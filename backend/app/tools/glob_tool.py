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
        self.security = security

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "Fast file pattern matching tool. Supports glob patterns like '**/*.py' or 'src/**/*.ts'. "
            "Returns matching file path relative to the search directory. "
            "Much faster than listing directories and filtering manually."
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
        parts = Path(rel_path).parts
        return any(part in self.EXCLUDED_DIRS for part in parts)

    def _format_matches(self, matches: list[dict]) -> str:
        lines = [f"找到 {len(matches)} 个文件:"]
        for m in matches[:MAX_RESULTS]:
            lines.append(m["path"])
        if len(matches) > MAX_RESULTS:
            lines.append(f"... 还有 {len(matches) - MAX_RESULTS} 个")
        return "\n".join(lines)
