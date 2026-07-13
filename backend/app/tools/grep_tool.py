import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import PureWindowsPath
from typing import Any

from app.security.path_security import ExternalPathError, PathSecurity
from app.tools.base import BaseTool, ToolResult, _external_path_approval

logger = logging.getLogger(__name__)

_HAS_RG = shutil.which("rg") is not None
_HAS_GREP = shutil.which("grep") is not None

MAX_MATCHES = 100
CONTEXT_LINES = 2


class GrepTool(BaseTool):
    """Fast content search tool using ripgrep (preferred) or grep subprocess."""

    EXCLUDED_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".mypy_cache",
        ".tox", ".eggs", ".idea", ".vscode",
    })

    def __init__(self, security: PathSecurity):
        self.security = security

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return (
            "Fast content search across files. Uses ripgrep if available, falls back to grep. "
            "Much faster than file search for finding patterns in codebases. "
            "Returns matching file paths, line numbers, and content."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (regex supported by ripgrep/grep)",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in (defaults to project root)",
                    },
                    "include": {
                        "type": "string",
                        "description": "File glob pattern to include (e.g. '*.py', '*.{ts,tsx}'). Only used for directory search.",
                    },
                },
                "required": ["pattern"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolResult(success=False, error="缺少 pattern 参数")

        raw_path = args.get("path", ".")
        include = args.get("include")

        try:
            validated_path = self.security.validate_path(raw_path)
        except ExternalPathError as exc:
            return _external_path_approval("grep", exc)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

        if _HAS_RG:
            return await self._search_ripgrep(validated_path, pattern, include)
        if _HAS_GREP:
            return await self._search_grep(validated_path, pattern, include)
        return await self._search_python(validated_path, pattern, include)

    async def _run_search_command(self, cmd: list[str], timeout: int = 30) -> tuple[bytes, bytes]:
        """执行搜索子进程并返回 stdout/stderr。

        函数名：_run_search_command
        入参：
          - cmd (list[str]): 需要执行的 rg/grep 命令参数列表
          - timeout (int): 子进程超时时间，单位秒
        功能：在 Windows 上使用线程池包装同步 subprocess.run，其他平台保留 asyncio 子进程。
        运行逻辑：
          1. Windows SelectorEventLoop 不支持 asyncio 子进程，因此切到 asyncio.to_thread。
          2. 非 Windows 继续使用 create_subprocess_exec，保持原有异步行为。
          3. 两条路径都返回原始 bytes，交给上层统一解析。
        出参：tuple[bytes, bytes] - stdout 与 stderr 的字节内容
        """
        if sys.platform == "win32":
            # Windows SelectorEventLoop 不实现子进程 API；同步 subprocess 放线程池避免阻塞事件循环。
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            return result.stdout, result.stderr

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)

    async def _search_ripgrep(self, path: str, pattern: str, include: str | None) -> ToolResult:
        cmd = [
            "rg",
            "--no-heading",
            "--line-number",
            "--color=never",
            f"--max-count={MAX_MATCHES}",
            f"--context={CONTEXT_LINES}",
        ]
        for d in self.EXCLUDED_DIRS:
            cmd.append(f"--glob=!{d}")
            cmd.append(f"--glob=!{d}/**")
        if include:
            for glob in include.split(","):
                cmd.append(f"--glob={glob.strip()}")
        cmd.extend([pattern, path])

        try:
            stdout, stderr = await self._run_search_command(cmd, timeout=30)
        except TimeoutError:
            return ToolResult(success=False, error="搜索超时 (30s)")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="搜索超时 (30s)")
        except FileNotFoundError:
            return await self._search_grep(path, pattern, include)

        output = stdout.decode("utf-8", errors="replace")
        if not output.strip():
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}'",
                data={"matches": [], "count": 0},
            )

        matches = self._parse_rg_output(output, path)
        matches = matches[:MAX_MATCHES]
        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches, "count": len(matches)},
        )

    async def _search_grep(self, path: str, pattern: str, include: str | None) -> ToolResult:
        cmd = ["grep", "-rn", "-E", f"--max-count={MAX_MATCHES}"]
        if include:
            # Git Bash grep 在 Windows subprocess(list argv) 下要求 --include=PATTERN，否则会把 PATTERN 当成位置参数。
            cmd.append(f"--include={include}")
        for d in self.EXCLUDED_DIRS:
            cmd.extend(["--exclude-dir", d])
        cmd.extend([pattern, path])

        try:
            stdout, stderr = await self._run_search_command(cmd, timeout=30)
        except TimeoutError:
            return ToolResult(success=False, error="搜索超时 (30s)")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="搜索超时 (30s)")
        except FileNotFoundError:
            return await self._search_python(path, pattern, include)

        output = stdout.decode("utf-8", errors="replace")
        if not output.strip():
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}'",
                data={"matches": [], "count": 0},
            )

        matches = self._parse_grep_output(output, path)
        matches = matches[:MAX_MATCHES]
        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches, "count": len(matches)},
        )

    async def _search_python(self, path: str, pattern: str, include: str | None) -> ToolResult:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(success=False, error=f"无效正则表达式: {e}")

        matches = []
        search_dir = path if os.path.isdir(path) else os.path.dirname(path)

        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS and not d.startswith(".")]
            for fname in files:
                if fname.startswith("."):
                    continue
                if include:
                    import fnmatch
                    if not fnmatch.fnmatch(fname, include.strip()):
                        continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if compiled.search(line):
                                matches.append({
                                    "file": os.path.relpath(fpath, search_dir),
                                    "line": i,
                                    "content": line.rstrip()[:200],
                                })
                                if len(matches) >= MAX_MATCHES:
                                    break
                except OSError:
                    continue
                if len(matches) >= MAX_MATCHES:
                    break

        if not matches:
            return ToolResult(
                success=True,
                output=f"未找到匹配 '{pattern}'",
                data={"matches": [], "count": 0},
            )

        display = self._format_matches(matches)
        return ToolResult(
            success=True,
            output=display,
            data={"matches": matches[:MAX_MATCHES], "count": min(len(matches), MAX_MATCHES)},
        )

    def _parse_rg_output(self, output: str, base_path: str) -> list[dict]:
        matches = []
        for line in output.splitlines():
            parsed = self._split_search_output_line(line, base_path, file_optional=os.path.isfile(base_path))
            if parsed is None:
                continue
            file_path, line_num, content = parsed
            rel = os.path.relpath(file_path, base_path) if not os.path.isabs(file_path) else file_path
            matches.append({"file": rel, "line": line_num, "content": content.strip()[:200]})
        return matches

    def _split_search_output_line(
        self,
        line: str,
        base_path: str,
        *,
        file_optional: bool = False,
    ) -> tuple[str, int, str] | None:
        """解析 rg/grep 的 `file:line:content` 输出行。

        函数名：_split_search_output_line
        入参：
          - line (str): rg/grep 输出的一行文本
          - base_path (str): 搜索目标路径，用于单文件搜索补齐文件名
          - file_optional (bool): 单文件 rg 输出可能省略文件名，仅输出 `line:content`
        功能：兼容 Windows 盘符中的冒号，避免把 `C:\...` 的盘符冒号误认为字段分隔符。
        运行逻辑：
          1. 优先处理单文件 rg 的 `line:content` 形式。
          2. 其余情况从右侧拆出 line/content，再在左侧保留完整文件路径。
          3. line 字段无法转为整数时返回 None，由调用方跳过。
        出参：tuple[str, int, str] | None - 文件路径、行号、内容，解析失败返回 None
        """
        if ":" not in line:
            return None

        if file_optional:
            line_num_text, content = line.split(":", 1)
            try:
                return base_path, int(line_num_text), content
            except ValueError:
                pass

        match = re.match(r"^(?P<file>(?:[A-Za-z]:)?[^:]*):(?P<line>\d+):(?P<content>.*)$", line)
        if match is None:
            return None
        file_path = match.group("file")
        if sys.platform == "win32" and PureWindowsPath(file_path).is_absolute():
            file_path = os.fspath(PureWindowsPath(file_path))
        return file_path, int(match.group("line")), match.group("content")

    def _parse_grep_output(self, output: str, base_path: str) -> list[dict]:
        matches = []
        for line in output.splitlines():
            parsed = self._split_search_output_line(line, base_path, file_optional=os.path.isfile(base_path))
            if parsed is None:
                continue
            file_path, line_num, content = parsed
            rel = os.path.relpath(file_path, base_path) if not os.path.isabs(file_path) else file_path
            matches.append({"file": rel, "line": line_num, "content": content.strip()[:200]})
        return matches

    def _format_matches(self, matches: list[dict]) -> str:
        if not matches:
            return "无匹配"
        lines = [f"找到 {len(matches)} 处匹配:"]
        for m in matches[:MAX_MATCHES]:
            lines.append(f"{m['file']}:{m['line']}: {m['content']}")
        if len(matches) > MAX_MATCHES:
            lines.append(f"... 还有 {len(matches) - MAX_MATCHES} 处")
        return "\n".join(lines)
