import logging
import os
from typing import Any

import aiofiles

from app.security.path_security import ExternalPathError, PathSecurity
from app.tools.base import BaseTool, ToolResult, _external_path_approval

logger = logging.getLogger(__name__)


class FileTool(BaseTool):
    """文件操作工具 - 支持分块读取"""

    EXCLUDED_SEARCH_DIRS = frozenset({"node_modules", "__pycache__", "venv"})
    SEARCHABLE_EXTENSIONS = frozenset(
        {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".h",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
        }
    )
    SEARCH_CONTEXT_LINES = 3
    MAX_FILE_SEARCH_OUTPUT = 10
    MAX_DIRECTORY_SEARCH_MATCHES = 50
    MAX_DIRECTORY_SEARCH_OUTPUT = 20
    MAX_LIST_DISPLAY_ITEMS = 15
    MAX_READ_BYTES = 50 * 1024
    MAX_LINE_LENGTH = 2000
    LINE_TRUNCATION_SUFFIX = "... (line truncated to 2000 chars)"

    def __init__(self, security: PathSecurity):
        self.security = security
        self.min_read_limit = 30
        self.default_read_limit = 500
        self.max_read_limit = 2000
        self._read_cache: dict[str, tuple[float, list[str]]] = {}
        self._read_cache_max = 128

    @property
    def name(self) -> str:
        return "file"

    @property
    def description(self) -> str:
        return "File read/write and directory operations tool, supports chunked reading of large files"

    def get_schema(self) -> dict[str, Any]:
        """返回工具的 JSON Schema"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "search", "list"],
                        "description": "Action type: read/search/list",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory path (relative or absolute)",
                    },
                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "For read: start line number (1-based), recommended with limit",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 30,
                        "maximum": 2000,
                        "default": 500,
                        "description": (
                            "For read: number of lines to read, recommended with start_line; "
                            "min 30, max 2000, default 500"
                        ),
                    },
                    "line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "For read: target line number, use with context to read surrounding lines; "
                            "omit when using start_line/limit"
                        ),
                    },
                    "context": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "For read: number of context lines, use with line; default 10 if omitted",
                    },
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": "For search: search keyword",
                    },

                },
                "required": ["action", "path"],
            },
            "examples": [
                {"action": "read", "path": "README.md"},
                {"action": "read", "path": "main.py", "start_line": 1, "limit": 80},
                {"action": "read", "path": "main.py", "line": 100, "context": 10},
                {"action": "search", "path": "main.py", "query": "def login"},
                {"action": "list", "path": "."},
            ],
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """执行文件操作"""
        action = args.get("action")

        if not action:
            return ToolResult(
                success=False,
                error="缺少必需参数: action。支持: read, list, search",
            )

        try:
            if action == "read":
                return await self._read_file(args)
            elif action == "list":
                return await self._list_directory(args)
            elif action == "search":
                return await self._search_in_file(args)
            else:
                return ToolResult(
                    success=False,
                    error=f"未知操作: {action}。支持: read, list, search",
                )

        except KeyError as e:
            return ToolResult(success=False, error=f"缺少必需参数: {e}")
        except Exception as e:
            logger.error("文件操作失败: %s", e)
            return ToolResult(success=False, error=str(e))

    def _get_cached_lines(self, path: str) -> list[str] | None:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._read_cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        return None

    def _set_cached_lines(self, path: str, lines: list[str]) -> None:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if len(self._read_cache) >= self._read_cache_max:
            oldest_key = next(iter(self._read_cache))
            del self._read_cache[oldest_key]
        self._read_cache[path] = (mtime, lines)

    async def _read_file(self, args: dict[str, Any]) -> ToolResult:
        try:
            path = self.security.validate_path(args["path"])
        except ExternalPathError as exc:
            return _external_path_approval("file", exc)

        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")

        if os.path.isdir(path):
            return ToolResult(success=False, error=f"路径是目录: {path}，请使用 list 操作")

        file_size = os.path.getsize(path)
        if file_size > self.MAX_READ_BYTES * 4:
            return ToolResult(
                success=False,
                error=f"文件过大 ({file_size} bytes)，超过 200KB 上限。请使用 grep 搜索特定内容。",
            )

        all_lines = self._get_cached_lines(path)
        if all_lines is None:
            async with aiofiles.open(path, encoding="utf-8", errors="replace") as f:
                all_lines = await f.readlines()
            self._set_cached_lines(path, all_lines)

        all_lines = [
            line.rstrip()[:self.MAX_LINE_LENGTH] + self.LINE_TRUNCATION_SUFFIX
            if len(line.rstrip()) > self.MAX_LINE_LENGTH
            else line.rstrip()
            for line in all_lines
        ]

        total_lines = len(all_lines)

        # 确定读取范围
        raw_end_line = args.get("end_line")
        start_line = self._positive_int(args.get("start_line"))
        end_line = self._positive_int(raw_end_line)
        line = self._positive_int(args.get("line"))
        context = self._positive_int(args.get("context")) or 10
        limit = self._read_limit(args.get("limit"))

        if start_line is not None:
            start_line = max(1, start_line)
            if limit is not None:
                end_line = min(total_lines, start_line + limit - 1)
            elif "end_line" in args and raw_end_line not in (None, ""):
                if end_line is None:
                    return ToolResult(success=False, error="结束行号必须大于等于起始行号")
                end_line = min(total_lines, end_line)
                if end_line < start_line:
                    return ToolResult(success=False, error="结束行号必须大于等于起始行号")
            else:
                end_line = min(total_lines, start_line + self.default_read_limit - 1)
        elif line is not None:
            # 读取指定行周围
            start_line = max(1, line - context)
            end_line = min(total_lines, line + context)
        else:
            # 读取全部（限制最大行数）
            start_line = 1
            end_line = min(total_lines, self.default_read_limit)

        # 提取目标行
        selected_lines = all_lines[start_line - 1 : end_line]

        # 构建输出
        output_lines = []
        for i, line_content in enumerate(selected_lines, start=start_line):
            output_lines.append(f"{i:4d}: {line_content}")

        content = "\n".join(output_lines)

        # 字节上限检查
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > self.MAX_READ_BYTES:
            while content_bytes > self.MAX_READ_BYTES and end_line > start_line + 1:
                end_line -= 1
                selected_lines = all_lines[start_line - 1 : end_line]
                output_lines = []
                for i, line_content in enumerate(selected_lines, start=start_line):
                    output_lines.append(f"{i:4d}: {line_content}")
                content = "\n".join(output_lines)
                content_bytes = len(content.encode("utf-8"))

        # 构建元信息
        meta = f"文件: {path}\n总行数: {total_lines}\n显示: 第 {start_line}-{end_line} 行"

        if total_lines > end_line:
            meta += (
                f"\n提示: 文件还有 {total_lines - end_line} 行未显示，"
                f"可使用 start_line={end_line + 1} 继续读取"
            )

        logger.info("读取文件: %s, 行 %s-%s/%s", path, start_line, end_line, total_lines)

        return ToolResult(
            success=True,
            output=f"{meta}\n\n{content}",
            data={
                "content": content,
                "path": path,
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": end_line,
                "has_more": total_lines > end_line,
            },
        )

    def _positive_int(self, value: Any) -> int | None:
        if value in (None, "") or isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _read_limit(self, value: Any) -> int | None:
        parsed = self._positive_int(value)
        if parsed is None:
            return None
        return max(self.min_read_limit, min(self.max_read_limit, parsed))

    async def _search_in_file(self, args: dict[str, Any]) -> ToolResult:
        try:
            path = self.security.validate_path(args["path"])
        except ExternalPathError as exc:
            return _external_path_approval("file", exc)
        query = args.get("query", "")

        if not query:
            return ToolResult(success=False, error="缺少 query 参数")

        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")

        if os.path.isdir(path):
            # 在目录下所有文件搜索
            return await self._search_in_directory(path, query)

        # 在单个文件搜索
        async with aiofiles.open(path, encoding="utf-8") as f:
            lines = await f.readlines()

        matches = []
        for i, line in enumerate(lines, 1):
            if query.lower() in line.lower():
                matches.append(
                    {"line": i, "content": line.rstrip(), "context": self._get_context(lines, i, 3)}
                )

        if not matches:
            return ToolResult(
                success=True,
                output=f"在 {path} 中未找到 '{query}'",
                data={"matches": [], "count": 0},
            )

        # 格式化输出
        output_parts = [f"在 {path} 中找到 {len(matches)} 处匹配:"]
        for m in matches[: self.MAX_FILE_SEARCH_OUTPUT]:
            output_parts.append(f"\n第 {m['line']} 行:")
            output_parts.append(m["context"])

        if len(matches) > self.MAX_FILE_SEARCH_OUTPUT:
            output_parts.append(f"\n... 还有 {len(matches) - self.MAX_FILE_SEARCH_OUTPUT} 处匹配")

        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            data={"matches": matches, "count": len(matches)},
        )

    def _get_context(self, lines: list[str], line_num: int, context: int) -> str:
        """获取行周围上下文"""
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)

        context_lines = []
        for i in range(start, end):
            prefix = ">>> " if i == line_num - 1 else "    "
            context_lines.append(f"{prefix}{i + 1:4d}: {lines[i].rstrip()}")

        return "\n".join(context_lines)

    async def _search_in_directory(self, dir_path: str, query: str) -> ToolResult:
        """在目录下搜索"""
        if not query:
            return ToolResult(success=False, error="缺少 query 参数")

        matches = []

        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [
                d for d in dirs if not d.startswith(".") and d not in self.EXCLUDED_SEARCH_DIRS
            ]

            for file in files:
                if file.startswith("."):
                    continue

                file_path = os.path.join(root, file)

                if not any(file.endswith(ext) for ext in self.SEARCHABLE_EXTENSIONS):
                    continue

                try:
                    async with aiofiles.open(file_path, encoding="utf-8") as f:
                        lines = await f.readlines()

                    for i, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            matches.append(
                                {"file": file_path, "line": i, "content": line.rstrip()[:100]}
                            )

                            if len(matches) >= self.MAX_DIRECTORY_SEARCH_MATCHES:
                                break
                except (OSError, UnicodeDecodeError):
                    continue

                if len(matches) >= self.MAX_DIRECTORY_SEARCH_MATCHES:
                    break

            if len(matches) >= self.MAX_DIRECTORY_SEARCH_MATCHES:
                break

        if not matches:
            return ToolResult(
                success=True,
                output=f"在 {dir_path} 中未找到 '{query}'",
                data={"matches": [], "count": 0},
            )

        output = f"找到 {len(matches)} 处匹配:\n"
        for m in matches[: self.MAX_DIRECTORY_SEARCH_OUTPUT]:
            rel_path = os.path.relpath(m["file"], dir_path)
            output += f"\n{rel_path}:{m['line']}: {m['content']}"

        if len(matches) > self.MAX_DIRECTORY_SEARCH_OUTPUT:
            output += f"\n... 还有 {len(matches) - self.MAX_DIRECTORY_SEARCH_OUTPUT} 处"

        return ToolResult(
            success=True, output=output, data={"matches": matches, "count": len(matches)}
        )



    async def _list_directory(self, args: dict[str, Any]) -> ToolResult:
        try:
            path = self.security.validate_path(args.get("path", "."))
        except ExternalPathError as exc:
            return _external_path_approval("file", exc)

        if not os.path.exists(path):
            return ToolResult(success=False, error=f"目录不存在: {path}")

        if not os.path.isdir(path):
            return ToolResult(success=False, error=f"不是目录: {path}")

        files: list[dict[str, str]] = []
        for item in sorted(os.listdir(path)):
            if item.startswith("."):
                continue
            item_path = os.path.join(path, item)
            files.append(
                {"name": item, "type": "directory" if os.path.isdir(item_path) else "file"}
            )

        logger.info("列出目录: %s, 共 %s 项", path, len(files))
        display_names = [
            f"{f['name']}({'d' if f['type'] == 'directory' else 'f'})"
            for f in files[: self.MAX_LIST_DISPLAY_ITEMS]
        ]
        output = f"目录 {path} 包含 {len(files)} 项: " + ", ".join(display_names)
        if len(files) > self.MAX_LIST_DISPLAY_ITEMS:
            output += f", ... 还有 {len(files) - self.MAX_LIST_DISPLAY_ITEMS} 项"
        return ToolResult(
            success=True, output=output, data={"files": files, "path": path, "count": len(files)}
        )


