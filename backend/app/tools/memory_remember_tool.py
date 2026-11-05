# 文件功能：memory_remember 工具——跨会话记忆的结构化写入入口
# 文件描述：让 Agent 免审批地把一条记忆追加到全局（~/.reflexion/memory.md）或
#          项目级（{project}/.reflexion/memory.md）记忆文件。全局记忆文件不在
#          PathSecurity 允许路径内（edit 工具写不了），本工具是写入全局档的唯一通道。
#          对齐 reflexion-os-studio 的 memory.remember 语义：单条单行、长度受限、
#          机密内容拒绝，仅 global/project 两档显式写入。
# 核心逻辑：内容校验（非空/单行/长度/机密启发式）→ 定位记忆文件 → 追加写入
#          （自动补前置换行），写入以追加语义进行、不覆盖既有条目。
import re
from pathlib import Path
from typing import Any

import aiofiles

from app.tools.base import BaseTool, ToolResult

# 单条记忆长度上限（字符数，对齐 Studio memory.remember 的 500 字限制）
MAX_MEMORY_CONTENT_CHARS = 500

# 机密内容启发式：命中即拒绝写入（记忆文件会被注入每次会话的 system prompt，
# 凭据一旦写入等于每次会话都在扩散）
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{10,}\b"),  # JWT 形态
    re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*\S+"),
]


def _contains_secret(content: str) -> str | None:
    """返回命中的机密模式说明；未命中返回 None。"""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(content):
            return pattern.pattern
    return None


class MemoryRememberTool(BaseTool):
    """把一条记忆追加写入全局或项目级 memory.md（免审批）。"""

    def __init__(self, *, project_root: str | None = None, global_dir: Path | None = None):
        """
        入参：
          - project_root (str | None): 当前项目根目录；为 None 时 project 档不可用
          - global_dir (Path | None): 全局 .reflexion 目录（默认 ~/.reflexion，测试可注入）
        """
        self._project_root = project_root
        self._global_dir = global_dir or (Path.home() / ".reflexion")

    @property
    def name(self) -> str:
        return "memory_remember"

    @property
    def description(self) -> str:
        return (
            "Persist one memory entry for future sessions: user preferences, project "
            "conventions, lessons learned. Writes a single line to the global or project "
            "memory.md file (append-only). Do NOT store secrets, temporary task state, or "
            "one-off conversation content. Max 500 characters per entry."
        )

    def _memory_path(self, scope: str) -> Path | None:
        """返回 scope 对应的记忆文件路径；scope=project 且无项目根时返回 None。"""
        if scope == "global":
            return self._global_dir / "memory.md"
        if scope == "project":
            if not self._project_root:
                return None
            return Path(self._project_root) / ".reflexion" / "memory.md"
        return None

    def get_schema(self) -> dict[str, Any]:
        """返回工具 schema：content（必填，单行 ≤500 字符）、scope（global/project，默认 project）。"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": (
                            "One memory entry, single line, max 500 characters. "
                            "Example: 用户偏好简洁中文回复，代码注释用中文"
                        ),
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["project", "global"],
                        "description": (
                            "project (default): applies to the current project only; "
                            "global: applies to all projects"
                        ),
                    },
                },
                "required": ["content"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """校验并追加一条记忆。

        逻辑：content 非空 → 单行 → 长度 ≤500 → 机密启发式拒绝 → 定位记忆文件 →
              目录创建 → 追加写入（前置换行补齐）
        出参：ToolResult，output 说明写入了哪个档位的哪个文件
        """
        content = args.get("content")
        if not isinstance(content, str) or not content.strip():
            return ToolResult(success=False, error="content 不能为空")

        content = content.strip()
        if "\n" in content or "\r" in content:
            return ToolResult(success=False, error="记忆条目必须单行，请拆分成多条分别写入")
        if len(content) > MAX_MEMORY_CONTENT_CHARS:
            return ToolResult(
                success=False,
                error=f"单条记忆不能超过 {MAX_MEMORY_CONTENT_CHARS} 字符（当前 {len(content)}），请提炼后写入",
            )
        secret_pattern = _contains_secret(content)
        if secret_pattern:
            return ToolResult(
                success=False,
                error="内容疑似凭据/机密（记忆文件会注入每次会话），拒绝写入",
            )

        scope = args.get("scope", "project")
        if scope not in {"project", "global"}:
            return ToolResult(success=False, error="scope must be 'project' or 'global'")
        memory_path = self._memory_path(scope)
        if memory_path is None:
            return ToolResult(success=False, error="当前会话未关联项目，无法写入项目级记忆")

        try:
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            existing = ""
            if memory_path.exists():
                existing = memory_path.read_text(encoding="utf-8")
            async with aiofiles.open(memory_path, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    await f.write("\n")
                await f.write(f"- {content}\n")
        except OSError as exc:
            return ToolResult(success=False, error=f"写入记忆文件失败: {exc}")

        return ToolResult(
            success=True,
            output=f"已记住（{scope}）：{content}",
            data={"scope": scope, "file": str(memory_path)},
        )
