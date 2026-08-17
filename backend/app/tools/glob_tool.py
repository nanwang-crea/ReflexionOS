"""
GlobTool — 文件名模式匹配工具（BaseTool 子类）。

基于 pathlib.Path.glob 实现快速文件名匹配（支持 '**/*.py' 等通配模式），
自动排除常见的构建产物/依赖/缓存目录，比手动遍历目录后过滤更快。
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from app.security.path_security import ExternalPathError, PathSecurity
from app.tools.base import BaseTool, ToolResult, _external_path_approval

logger = logging.getLogger(__name__)

MAX_RESULTS = 100


class GlobTool(BaseTool):
    """Fast file pattern matching tool using pathlib.glob."""

    EXCLUDED_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".mypy_cache",
        ".tox", ".eggs", ".idea", ".vscode",
    })

    def __init__(self, security: PathSecurity):
        """初始化 Glob 工具。入参：security - 路径安全校验器，用于限制可搜索的目录范围"""
        self.security = security

    @property
    def name(self) -> str:
        """工具名称，固定为 'glob'，用于 LLM 的 tool_calls 识别"""
        return "glob"

    @property
    def description(self) -> str:
        """工具描述，告知 LLM 支持的通配模式及相对于手动列目录过滤的优势"""
        return (
            "Fast file pattern matching tool. Supports glob patterns like '**/*.py' or 'src/**/*.ts'. "
            "Returns matching file path relative to the search directory. "
            "Much faster than listing directories and filtering manually."
        )

    def get_schema(self) -> dict[str, Any]:
        """返回工具的 JSON Schema：pattern（必填，glob 模式）、path（可选，搜索目录，默认项目根）"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files (e.g. '**/*.py', 'src/**/*.ts', '*.md')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (defaults to project root)",
                    },
                },
                "required": ["pattern"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """
        Glob 工具主入口。

        入参：args 需含 pattern（glob 模式）；可选 path（搜索目录，默认当前目录）
        逻辑：校验搜索路径（越权访问项目外路径时转为审批请求）-> 校验路径为目录 ->
            在线程池中执行同步的 _glob 遍历（避免阻塞事件循环）-> 格式化结果
        返回：ToolResult，data 中 matches 最多截断到 MAX_RESULTS 条，count 为实际匹配总数
        """
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(success=False, error="缺少 pattern 参数")

        raw_path = args.get("path", ".")

        try:
            validated_path = self.security.validate_path(raw_path)
        except ExternalPathError as exc:
            return _external_path_approval("glob", exc)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        if not os.path.isdir(validated_path):
            return ToolResult(success=False, error=f"不是目录: {validated_path}")

        matches = await asyncio.to_thread(self._glob, validated_path, pattern)

        if not matches:
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}' 的文件",
                data={"matches": [], "count": 0},
            )

        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches[:MAX_RESULTS], "count": len(matches)},
        )

    def _glob(self, base_path: str, pattern: str) -> list[dict]:
        """
        同步执行 glob 匹配（供 asyncio.to_thread 调度，避免阻塞事件循环）。

        入参：base_path - 搜索起始目录（已校验的绝对路径）；pattern - glob 模式
        逻辑：用 Path.glob 遍历匹配项，跳过目录（只返回文件）和被排除目录下的路径
            （_is_excluded），达到 MAX_RESULTS 上限即停止收集；glob 抛 OSError 时静默忽略
        返回：按相对路径排序的匹配列表，每项含 path（相对路径）和 name（文件名）
        """
        base = Path(base_path)
        results = []
        try:
            for p in base.glob(pattern):
                if p.is_dir():
                    continue
                rel = os.path.relpath(str(p), base_path)
                if self._is_excluded(rel):
                    continue
                results.append({"path": rel, "name": p.name})
                if len(results) >= MAX_RESULTS:
                    break
        except OSError:
            pass
        return sorted(results, key=lambda m: m["path"])

    def _is_excluded(self, rel_path: str) -> bool:
        """判断相对路径是否位于排除目录（EXCLUDED_DIRS）之下：路径任一层级命中即排除"""
        parts = Path(rel_path).parts
        return any(part in self.EXCLUDED_DIRS for part in parts)

    def _format_matches(self, matches: list[dict]) -> str:
        """将匹配结果格式化为面向 LLM/用户展示的文本，最多列出 MAX_RESULTS 条并提示剩余数量"""
        lines = [f"找到 {len(matches)} 个文件:"]
        for m in matches[:MAX_RESULTS]:
            lines.append(m["path"])
        if len(matches) > MAX_RESULTS:
            lines.append(f"... 还有 {len(matches) - MAX_RESULTS} 个")
        return "\n".join(lines)
