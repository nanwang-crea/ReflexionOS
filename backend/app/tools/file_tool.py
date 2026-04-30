import logging
import os
from typing import Any

import aiofiles

from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult

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

    def __init__(self, security: PathSecurity):
        self.security = security
        self.min_read_limit = 30
        self.default_read_limit = 80
        self.max_read_limit = 100

    @property
    def name(self) -> str:
        return "file"

    @property
    def description(self) -> str:
        return "文件读写和目录操作工具，支持分块读取大文件"

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
                        "enum": ["read", "search", "write", "list", "delete"],
                        "description": "操作类型：read/search/write/list/delete",
                    },
                    "path": {
                        "type": "string",
                        "description": "文件或目录路径（相对或绝对）",
                    },
                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "read 使用：起始行号（从1开始），推荐与 limit 一起使用",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 30,
                        "maximum": 100,
                        "default": 80,
                        "description": (
                            "read 使用：读取行数，推荐与 start_line 一起使用；"
                            "最小 30，最大 100，默认 80"
                        ),
                    },
                    "line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "read 使用：目标行号，配合 context 使用读取周围行；"
                            "使用 start_line/limit 时请省略"
                        ),
                    },
                    "context": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "read 使用：上下文行数，配合 line 使用；省略时默认 10",
                    },
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": "search 使用：搜索关键词",
                    },
                    "content": {
                        "type": "string",
                        "description": "write 使用：写入的内容",
                    },
                },
                "required": ["action", "path"],
            },
            "examples": [
                {"action": "read", "path": "README.md"},
                {"action": "read", "path": "main.py", "start_line": 1, "limit": 80},
                {"action": "read", "path": "main.py", "line": 100, "context": 10},
                {"action": "search", "path": "main.py", "query": "def login"},
                {"action": "write", "path": "hello.py", "content": "print('hello')"},
                {"action": "list", "path": "."},
            ],
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """执行文件操作"""
        action = args.get("action")

        try:
            if action == "read":
                return await self._read_file(args)
            elif action == "write":
                return await self._write_file(args)
            elif action == "list":
                return await self._list_directory(args)
            elif action == "delete":
                return await self._delete_file(args)
            elif action == "search":
                return await self._search_in_file(args)
            else:
                return ToolResult(
                    success=False,
                    error=f"未知操作: {action}。支持: read, write, list, delete, search",
                )

        except KeyError as e:
            return ToolResult(success=False, error=f"缺少必需参数: {e}")
        except Exception as e:
            logger.error("文件操作失败: %s", e)
            return ToolResult(success=False, error=str(e))

    async def _read_file(self, args: dict[str, Any]) -> ToolResult:
        """读取文件内容 - 支持分块读取"""
        path = self.security.validate_path(args["path"])

        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")

        if os.path.isdir(path):
            return ToolResult(success=False, error=f"路径是目录: {path}，请使用 list 操作")

        # 读取文件所有行
        async with aiofiles.open(path, encoding="utf-8") as f:
            all_lines = await f.readlines()

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
            output_lines.append(f"{i:4d}: {line_content.rstrip()}")

        content = "\n".join(output_lines)

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
        """在文件中搜索内容"""
        path = self.security.validate_path(args["path"])
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

    async def _write_file(self, args: dict[str, Any]) -> ToolResult:
        """写入文件内容"""
        path = self.security.validate_write_path(args["path"])
        if "content" not in args:
            return ToolResult(success=False, error="缺少 content 参数")
        content = args.get("content", "")

        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        async with aiofiles.open(path, mode="w", encoding="utf-8") as f:
            await f.write(content)

        logger.info("写入文件: %s", path)
        return ToolResult(success=True, output=f"文件已写入: {path}")

    async def _list_directory(self, args: dict[str, Any]) -> ToolResult:
        """列出目录内容"""
        path = self.security.validate_path(args.get("path", "."))

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

    async def _delete_file(self, args: dict[str, Any]) -> ToolResult:
        """删除文件"""
        path = self.security.validate_write_path(args["path"])

        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")

        if os.path.isdir(path):
            os.rmdir(path)
            logger.info("删除目录: %s", path)
            return ToolResult(success=True, output=f"目录已删除: {path}")

        os.remove(path)
        logger.info("删除文件: %s", path)
        return ToolResult(success=True, output=f"文件已删除: {path}")
