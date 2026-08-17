"""
ExploreTool — 代码库探索聚合工具（BaseTool 子类）。

接收自然语言查询，内部从中提取关键词，聚合调用 GlobTool（文件名匹配）与
GrepTool（内容匹配）并汇总结果，替代 Agent 手动多次调用 glob/grep 来
快速了解某个模块或定位相关代码。
"""
import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ExploreTool(BaseTool):
    """聚合 glob + grep 的代码探索工具"""

    def __init__(self, path_security: Any = None):
        """
        初始化探索工具。

        入参：path_security - 路径安全校验器，为 None 时不创建内部子工具
            （此时 execute 会因缺少子工具而始终返回空结果）
        逻辑：若提供了 path_security，则据此构造内部使用的 FileTool/GrepTool/GlobTool 实例
        """
        self._path_security = path_security
        self._file_tool = None
        self._grep_tool = None
        self._glob_tool = None
        if path_security:
            from app.tools.file_tool import FileTool
            from app.tools.glob_tool import GlobTool
            from app.tools.grep_tool import GrepTool
            self._file_tool = FileTool(path_security)
            self._grep_tool = GrepTool(path_security)
            self._glob_tool = GlobTool(path_security)

    @property
    def name(self) -> str:
        """工具名称，固定为 'explore'，用于 LLM 的 tool_calls 识别"""
        return "explore"

    @property
    def description(self) -> str:
        """工具描述，告知 LLM 该工具适合替代多次独立的 glob/grep/file 调用"""
        return (
            "Search the codebase and return a structured summary. "
            "Provide a natural language query describing what you want to find. "
            "Internally runs glob, grep, and file read to aggregate results. "
            "Use this instead of multiple separate grep/glob/file calls when you "
            "need to quickly understand a module, find related files, or locate code."
        )

    def get_schema(self) -> dict[str, Any]:
        """返回工具的 JSON Schema：query（必填，自然语言查询）、paths（可选，限定搜索目录列表）"""
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
        """
        探索工具主入口。

        入参：args 需包含 query（自然语言查询），可选 paths（限定搜索的目录列表）
        逻辑：从 query 中提取关键词（去停用词）拼成 "|" 分隔的正则模式 ->
            分别调用内部 glob（文件名匹配）和 grep（内容匹配）-> 拼接两部分结果
        返回：ToolResult，output 为聚合后的 Markdown 格式文本；无匹配时提示未找到
        """
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
        """从自然语言查询中提取关键词：去除常见英文停用词和单字符词，返回剩余词列表"""
        stop_words = {
            "how", "does", "the", "a", "an", "is", "are", "what", "where",
            "which", "who", "when", "why", "do", "can", "all",
            "find", "search", "look", "for", "in", "on", "to", "from",
            "and", "or", "of", "with", "by", "that", "this", "it",
            "works", "work", "related", "about",
        }
        words = query.lower().replace(",", " ").replace(".", " ").split()
        return [w for w in words if w not in stop_words and len(w) > 1]

    async def _run_glob(self, pattern: str, paths: list[str]) -> str | None:
        """
        调用内部 GlobTool 按文件名模式搜索（模式两端补 * 做子串匹配）。

        入参：pattern - 关键词拼接的搜索模式；paths - 可选目录限定（仅取第一个）
        逻辑：GlobTool 未初始化或调用异常时静默返回 None（不影响 explore 整体结果）；
            成功时截取前 20 行输出
        返回：格式化后的匹配文本，或 None（无子工具/无结果/异常）
        """
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
        """
        调用内部 GrepTool 按正则模式搜索文件内容。

        入参：pattern - 关键词拼接的正则搜索模式；paths - 可选目录限定（仅取第一个）
        逻辑：与 _run_glob 类似，GrepTool 未初始化或异常时静默返回 None；
            成功时截取前 30 行输出
        返回：格式化后的匹配文本，或 None（无子工具/无结果/异常）
        """
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
