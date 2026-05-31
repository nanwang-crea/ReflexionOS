import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ExploreTool(BaseTool):

    def __init__(self, path_security: Any = None):
        self._path_security = path_security
        self._file_tool = None
        self._grep_tool = None
        self._glob_tool = None
        if path_security:
            from app.tools.file_tool import FileTool
            from app.tools.grep_tool import GrepTool
            from app.tools.glob_tool import GlobTool
            self._file_tool = FileTool(path_security)
            self._grep_tool = GrepTool(path_security)
            self._glob_tool = GlobTool(path_security)

    @property
    def name(self) -> str:
        return "explore"

    @property
    def description(self) -> str:
        return (
            "Search the codebase and return a structured summary. "
            "Provide a natural language query describing what you want to find. "
            "Internally runs glob, grep, and file read to aggregate results. "
            "Use this instead of multiple separate grep/glob/file calls when you "
            "need to quickly understand a module, find related files, or locate code."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of what to search for (e.g., 'how authentication works', 'all API route handlers')",
                    },
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of directory paths to limit the search scope",
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        if not query:
            return ToolResult(success=False, error="query parameter is required")

        paths = args.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]

        keywords = self._extract_keywords(query)
        pattern = "|".join(keywords[:5]) if keywords else query

        results = []

        glob_result = await self._run_glob(pattern, paths)
        if glob_result:
            results.append(f"## Files matching '{pattern}':\n{glob_result}")

        grep_result = await self._run_grep(pattern, paths)
        if grep_result:
            results.append(f"## Code matches for '{pattern}':\n{grep_result}")

        if not results:
            return ToolResult(
                success=True,
                output=f"No results found for query: {query}",
            )

        return ToolResult(
            success=True,
            output="\n\n".join(results),
        )

    def _extract_keywords(self, query: str) -> list[str]:
        stop_words = {
            "how", "does", "the", "a", "an", "is", "are", "what", "where",
            "which", "who", "when", "why", "do", "does", "can", "all",
            "find", "search", "look", "for", "in", "on", "to", "from",
            "and", "or", "of", "with", "by", "that", "this", "it",
            "works", "work", "related", "about",
        }
        words = query.lower().replace(",", " ").replace(".", " ").split()
        return [w for w in words if w not in stop_words and len(w) > 1]

    async def _run_glob(self, pattern: str, paths: list[str]) -> str | None:
        if self._glob_tool is None:
            return None
        try:
            search_path = paths[0] if paths else None
            result = await self._glob_tool.execute({
                "pattern": f"*{pattern}*",
                "path": search_path,
            })
            if result.success and result.output:
                lines = result.output.strip().split("\n")
                return "\n".join(lines[:20])
        except Exception:
            logger.debug("explore glob failed", exc_info=True)
        return None

    async def _run_grep(self, pattern: str, paths: list[str]) -> str | None:
        if self._grep_tool is None:
            return None
        try:
            search_path = paths[0] if paths else None
            result = await self._grep_tool.execute({
                "pattern": pattern,
                "path": search_path,
            })
            if result.success and result.output:
                lines = result.output.strip().split("\n")
                return "\n".join(lines[:30])
        except Exception:
            logger.debug("explore grep failed", exc_info=True)
        return None
