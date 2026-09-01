"""
FileTool — 文件读取/搜索/目录列表工具（BaseTool 子类）。

提供三种操作：read（支持按行号范围或目标行+上下文的分块读取，含缓存和字节上限截断）、
search（在单文件或整个目录中做大小写不敏感的关键词搜索）、list（列出目录条目）。
所有路径访问都经过 PathSecurity 校验，越权访问项目外路径时转换为审批请求。
"""
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
        """
        初始化文件工具。

        入参：security - 路径安全校验器
        逻辑：设置读取行数上下限（min/default/max_read_limit），初始化基于
            文件 mtime 的按行缓存（_read_cache），避免同一文件短时间内重复整读。
        """
        self.security = security
        self.min_read_limit = 30
        self.default_read_limit = 500
        self.max_read_limit = 2000
        self._read_cache: dict[str, tuple[float, list[str]]] = {}
        self._read_cache_max = 128

    @property
    def name(self) -> str:
        """工具名称，固定为 'file'，用于 LLM 的 tool_calls 识别"""
        return "file"

    @property
    def description(self) -> str:
        """工具描述，告知 LLM 支持分块读取大文件"""
        return "File read/write and directory operations tool, supports chunked reading of large files"

    def get_schema(self) -> dict[str, Any]:
        """
        返回工具的 JSON Schema，传递给 LLM 的 tools 参数。

        出参：dict，定义 action（枚举 read/search/list）、path 及各 action 专属参数
            （read 的 start_line/limit/line/context，search 的 query）。
            注：properties 中的 description 是面向 LLM 的功能说明，保持英文原文不译。
        """
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
        """执行文件操作。入参：args 需含 action（read/list/search）及各 action 所需参数（见 get_schema）。
        逻辑：按 action 分发到 _read_file/_list_directory/_search_in_file，统一捕获异常。
        返回：ToolResult，失败时 error 说明缺参或异常原因。"""
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
        """按文件 mtime 校验缓存是否仍然有效；有效则返回缓存的行列表，否则返回 None（需要重新读取）"""
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._read_cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        return None

    def _set_cached_lines(self, path: str, lines: list[str]) -> None:
        """将文件行列表写入缓存（以当前 mtime 为 key 校验依据），超过容量上限时淘汰最早的一条（简单 FIFO）"""
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if len(self._read_cache) >= self._read_cache_max:
            oldest_key = next(iter(self._read_cache))
            del self._read_cache[oldest_key]
        self._read_cache[path] = (mtime, lines)

    async def _read_file(self, args: dict[str, Any]) -> ToolResult:
        """
        read 动作实现：分块读取文件内容。

        入参：args 需含 path；可选 start_line+limit（或 end_line）按行号范围读取，
            或 line+context 读取目标行及其上下文，两者都不给则从头读取默认行数
        逻辑：校验路径与文件存在性 -> 超过 200KB 直接拒绝（建议改用 grep）->
            优先读缓存，未命中则整读文件并按 mtime 缓存 -> 截断超长行 ->
            根据参数计算实际读取的 [start_line, end_line] 区间 -> 拼接带行号的输出 ->
            若输出字节数超过 MAX_READ_BYTES 上限则逐步收窄 end_line 直至满足限制
        返回：ToolResult，output 含元信息（总行数/显示范围/是否还有更多）与内容，
            data 中包含结构化字段供程序化使用
        """
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
        """将输入值安全转换为正整数：None/空字符串/布尔值/非法数值/非正数均返回 None"""
        if value in (None, "") or isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _read_limit(self, value: Any) -> int | None:
        """解析 limit 参数并夹取到 [min_read_limit, max_read_limit] 范围内；无效输入返回 None"""
        parsed = self._positive_int(value)
        if parsed is None:
            return None
        return max(self.min_read_limit, min(self.max_read_limit, parsed))

    async def _search_in_file(self, args: dict[str, Any]) -> ToolResult:
        """
        search 动作实现：在单文件或整个目录中做大小写不敏感的关键词搜索。

        入参：args 需含 path、query（搜索关键词）
        逻辑：path 为目录时委托给 _search_in_directory；为文件时逐行做子串匹配，
            命中行附带上下文（_get_context），最多展示 MAX_FILE_SEARCH_OUTPUT 条
        返回：ToolResult，data 中包含全部匹配（matches）与匹配总数（count）
        """
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
        """
        目录级搜索：递归遍历目录下的可搜索文本文件，做关键词匹配。

        入参：dir_path - 目标目录（已校验）；query - 搜索关键词
        逻辑：os.walk 遍历，跳过隐藏目录/EXCLUDED_SEARCH_DIRS（如 node_modules）和隐藏文件，
            仅搜索 SEARCHABLE_EXTENSIONS 白名单后缀的文件；单文件读取/解码失败则跳过该文件；
            达到 MAX_DIRECTORY_SEARCH_MATCHES 上限即提前终止遍历
        返回：ToolResult，output 展示相对路径:行号:内容，超出 MAX_DIRECTORY_SEARCH_OUTPUT 提示还有更多；
            data 中包含全部匹配（matches，内容截断至 100 字符）与匹配总数
        """
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
        """
        list 动作实现：列出目录下的一级条目（不递归）。

        入参：args 可含 path（默认为项目根 "."）
        逻辑：校验路径存在且为目录 -> 排序后遍历，跳过隐藏项 -> 标注每项是文件还是目录
        返回：ToolResult，output 为摘要文本（最多展示 MAX_LIST_DISPLAY_ITEMS 项），
            data 中包含完整的 files 列表与总数
        """
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


