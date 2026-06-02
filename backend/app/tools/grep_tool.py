import asyncio
import logging
import os
import re
import shutil
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
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except TimeoutError:
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
            cmd.extend(["--include", include])
        for d in self.EXCLUDED_DIRS:
            cmd.extend(["--exclude-dir", d])
        cmd.extend([pattern, path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except TimeoutError:
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
            if ":" not in line:
                continue
            parts = line.split(":", 2)
            if os.path.isfile(base_path):
                file_path = base_path
                line_num = parts[0]
                content = line.split(":", 1)[1]
            elif len(parts) >= 3:
                file_path, line_num, content = parts[0], parts[1], parts[2]
            else:
                continue
            try:
                line_num = int(line_num)
            except ValueError:
                continue
            rel = os.path.relpath(file_path, base_path) if not os.path.isabs(file_path) else file_path
            matches.append({"file": rel, "line": line_num, "content": content.strip()[:200]})
        return matches

    def _parse_grep_output(self, output: str, base_path: str) -> list[dict]:
        matches = []
        for line in output.splitlines():
            if ":" not in line:
                continue
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            file_path, line_num, content = parts[0], parts[1], parts[2]
            try:
                line_num = int(line_num)
            except ValueError:
                continue
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
