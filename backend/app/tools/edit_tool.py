"""
EditTool — 文件编辑工具（BaseTool 子类）。

提供三种编辑动作：str_replace（字符串精确/模糊替换，推荐）、
patch（应用 Unified Diff 或 Codex 风格补丁）、write（整文件写入，仅用于新建文件）。
统一处理换行符（CRLF/LF）保留、路径安全校验（PathSecurity）与按文件路径的并发锁，
避免并发编辑同一文件时相互覆盖。
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import aiofiles

from app.errors import ValidationError
from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult
from app.tools.diff_parser import CodexPatchParser, DiffParser
from app.tools.replacer import replace

logger = logging.getLogger(__name__)

# 按文件路径缓存的 asyncio.Lock，保证同一文件的并发编辑串行执行
_file_locks: dict[str, asyncio.Lock] = {}


def _get_lock(path: str) -> asyncio.Lock:
    """获取（或按需创建）指定文件路径对应的进程内异步锁，用于串行化同文件的编辑操作"""
    if path not in _file_locks:
        _file_locks[path] = asyncio.Lock()
    return _file_locks[path]


def _detect_line_ending(content: str) -> str:
    """从字符串内容中检测换行符风格：含 \\r\\n 则判定为 CRLF，否则为 LF"""
    if "\r\n" in content:
        return "\r\n"
    return "\n"


def _detect_line_ending_from_bytes(raw: bytes) -> str:
    """从原始字节内容中检测换行符风格，用于写回文件时保持原有换行符不变"""
    if b"\r\n" in raw:
        return "\r\n"
    return "\n"


def _read_file_bytes_sync(path: str) -> bytes:
    """以二进制读取文件全部字节（同步，供 asyncio.to_thread 调度）。

    输入：path 文件路径
    作用：用 with 语句打开文件并读取，保证 read 抛异常时文件句柄被关闭
    返回：文件原始字节
    """
    with open(path, "rb") as f:
        return f.read()


def _normalize_to_lf(text: str) -> str:
    """将文本中的 CRLF 统一替换为 LF，便于后续做纯 LF 语境下的字符串替换/diff 匹配"""
    return text.replace("\r\n", "\n")


def _convert_line_ending(text: str, ending: str) -> str:
    """将已归一化为 LF 的文本按需转换回目标换行符（写回文件前调用，保持原文件风格）"""
    if ending == "\r\n":
        return text.replace("\n", "\r\n")
    return text


class EditTool(BaseTool):
    """文件编辑工具：str_replace/patch/write 三种动作的统一入口"""

    def __init__(self, security: PathSecurity):
        """
        初始化编辑工具。

        入参：security - 路径安全校验器，用于限制可写路径范围
        逻辑：保存安全校验器，创建 Unified Diff 与 Codex 补丁两种解析器实例
        """
        self.security = security
        self.parser = DiffParser()
        self.codex_parser = CodexPatchParser()

    @property
    def name(self) -> str:
        """工具名称，固定为 'edit'，用于 LLM 的 tool_calls 识别"""
        return "edit"

    @property
    def description(self) -> str:
        """工具描述，告知 LLM 三种 action 的适用场景"""
        return (
            "File edit tool. Prefer str_replace for precise or fuzzy replacement; "
            "patch for complex multi-line diff edits; write ONLY for creating new files."
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """
        编辑工具统一入口，按 action 分发到具体实现。

        入参：
            args: 工具调用参数，必须包含 action（str_replace/patch/write）与 path，
                其余字段按 action 不同而不同（见 get_schema）
        逻辑：校验 action/path 是否存在 -> 分发到 _str_replace/_patch/_write ->
            捕获异常并转换为失败的 ToolResult
        返回：ToolResult，成功时 output 描述操作结果，失败时 error 说明原因
        """
        action = args.get("action")
        path = args.get("path")
        if not action:
            return ToolResult(success=False, error="缺少 action 参数")
        if not path:
            return ToolResult(success=False, error="缺少 path 参数")
        try:
            if action == "str_replace":
                return await self._str_replace(args)
            elif action == "patch":
                return await self._patch(args)
            elif action == "write":
                return await self._write(args)
            else:
                return ToolResult(success=False, error=f"未知 action: {action}")
        except Exception as e:
            logger.error("Edit 执行失败: %s", e)
            return ToolResult(success=False, error=str(e))

    async def _str_replace(self, args: dict[str, Any]) -> ToolResult:
        """
        str_replace 动作实现：在目标文件中做字符串替换（支持模糊匹配，见 replacer.replace）。

        入参：args 需包含 path、old_string、new_string，可选 replace_all（默认 False）；
            old_string 为空字符串时表示追加内容到文件末尾或新建文件
        逻辑：校验路径与参数 -> 加文件锁 -> 读取原始字节检测换行符 -> 归一化为 LF 后
            调用 replace() 做替换 -> 转换回原换行符 -> 写回文件
        返回：成功时 output 提示替换完成，失败时 error 说明原因（如未找到匹配、多处匹配等）
        """
        path = self.security.validate_write_path(args["path"])
        old_string = args.get("old_string")
        new_string = args.get("new_string")

        if old_string is None:
            return ToolResult(success=False, error="缺少 old_string 参数")
        if new_string is None:
            return ToolResult(success=False, error="缺少 new_string 参数")
        if old_string == new_string:
            return ToolResult(success=False, error="old_string 和 new_string 不能相同")
        replace_all = bool(args.get("replace_all", False))

        lock = _get_lock(path)
        async with lock:
            if old_string == "":
                return await self._append_or_create_locked(path, new_string)

            if not os.path.exists(path):
                return ToolResult(success=False, error=f"文件不存在: {path}")
            if os.path.isdir(path):
                return ToolResult(success=False, error=f"路径是目录: {path}")

            raw_bytes = await asyncio.to_thread(_read_file_bytes_sync, path)
            line_ending = _detect_line_ending_from_bytes(raw_bytes)

            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
            normalized_content = _normalize_to_lf(content)
            normalized_old = _normalize_to_lf(old_string)
            normalized_new = _normalize_to_lf(new_string)

            try:
                result = replace(normalized_content, normalized_old, normalized_new, replace_all)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))

            result = _convert_line_ending(result, line_ending)

            async with aiofiles.open(path, "w", encoding="utf-8", newline="") as f:
                await f.write(result)

        return ToolResult(
            success=True,
            output=f"成功替换 {path}",
            data={"file": path, "action": "str_replace", "replace_all": replace_all},
        )

    async def _append_or_create(self, path: str, new_string: str) -> ToolResult:
        """加锁后委托给 _append_or_create_locked；供未持有该文件锁的调用方使用"""
        lock = _get_lock(path)
        async with lock:
            return await self._append_or_create_locked(path, new_string)

    async def _append_or_create_locked(self, path: str, new_string: str) -> ToolResult:
        """
        在已持有文件锁的前提下，追加内容到已存在文件末尾，或在文件不存在时新建文件。

        入参：path - 目标文件路径（已校验）；new_string - 要写入/追加的内容
        逻辑：若目录不存在则创建 -> 文件已存在时读取原内容检测换行符，若末尾无换行则先补一个，
            再拼接归一化并转换回原换行符的新内容 -> 文件不存在则直接创建并写入
        返回：ToolResult，output 说明是"追加"还是"创建"
        """
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        if os.path.exists(path):
            raw_bytes = await asyncio.to_thread(_read_file_bytes_sync, path)
            line_ending = _detect_line_ending_from_bytes(raw_bytes)
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
            normalized_new = _normalize_to_lf(new_string)
            if not content.endswith("\n"):
                content += line_ending
            content += _convert_line_ending(normalized_new, line_ending)
            # Windows 文本模式会把 \n 再转换成 \r\n；newline="" 可保留上面显式转换出的 CRLF。
            async with aiofiles.open(path, "w", encoding="utf-8", newline="") as f:
                await f.write(content)
            return ToolResult(
                success=True,
                output=f"成功追加内容到 {path}",
                data={"file": path, "action": "str_replace"},
            )

        normalized_new = _normalize_to_lf(new_string)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(normalized_new)
        return ToolResult(
            success=True,
            output=f"成功创建文件 {path}",
            data={"file": path, "action": "str_replace"},
        )

    async def _patch(self, args: dict[str, Any]) -> ToolResult:
        """
        patch 动作实现：根据补丁文本格式自动分发到对应解析/应用逻辑。

        入参：args 需包含 patch（补丁文本）
        逻辑：若文本包含 "*** Begin Patch" 则视为 Codex 风格，走 _execute_codex_patch；
            否则按 Unified Diff 处理，走 _execute_unified_diff
        返回：ToolResult，见两个具体方法的说明
        """
        patch_text = args.get("patch")
        if not patch_text:
            return ToolResult(success=False, error="缺少 patch 参数")
        if self.codex_parser.is_codex_style(patch_text):
            return await self._execute_codex_patch(patch_text)
        return await self._execute_unified_diff(patch_text)

    async def _execute_unified_diff(self, patch_text: str) -> ToolResult:
        """
        应用 Unified Diff 格式的补丁（仅支持单文件）。

        入参：patch_text - Unified Diff 文本
        逻辑：提取补丁涉及的文件路径（要求唯一）-> 解析出 Hunk 列表 -> 校验目标路径 ->
            加文件锁读取原文件行（不存在则视为空文件）-> 逆序应用各 hunk（_apply_hunks）->
            若有 hunk 应用失败（内容不匹配）则返回冲突错误，否则写回文件
        返回：成功时 output 说明应用了多少个修改；失败时 error 说明冲突数量
        """
        file_paths = self.parser.extract_file_paths(patch_text)
        unique_file_paths = list(dict.fromkeys(file_paths))
        if len(unique_file_paths) > 1:
            return ToolResult(success=False, error="Unified Diff 仅支持单文件 patch")

        hunks = self.parser.parse(patch_text)
        if not hunks:
            return ToolResult(success=False, error="无法解析 Unified Diff")

        file_path = self.parser.extract_file_path(patch_text)
        if not file_path:
            return ToolResult(success=False, error="无法提取文件路径")
        file_path = self.security.validate_write_path(file_path)

        lock = _get_lock(file_path)
        async with lock:
            try:
                with open(file_path, encoding="utf-8") as f:
                    original_lines = f.readlines()
            except FileNotFoundError:
                original_lines = []

            result_lines, applied, rejected = self._apply_hunks(original_lines, hunks)

            if rejected > 0:
                return ToolResult(
                    success=False,
                    error=f"Patch 冲突: {rejected}/{len(hunks)} 个修改无法应用",
                    data={"file": file_path, "hunks_applied": applied, "hunks_rejected": rejected},
                )

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(result_lines)

        return ToolResult(
            success=True,
            output=f"成功应用 {applied} 个修改到 {file_path}",
            data={"file": file_path, "hunks_applied": applied, "hunks_rejected": rejected},
        )

    async def _execute_codex_patch(self, patch_text: str) -> ToolResult:
        """
        应用 Codex 风格补丁（Add/Update/Delete File 三种操作之一）。

        入参：patch_text - Codex 风格补丁文本
        逻辑：用 CodexPatchParser 解析出 CodexPatch -> 校验目标路径 -> 加文件锁 ->
            按 action 分支处理：
              add    - 目标已存在则报错，否则创建并写入内容；
              delete - 目标不存在/是目录则报错，否则删除文件；
              update - 读取原文件行，依次应用每个 hunk（_apply_codex_hunk），
                       任一 hunk 失败立即返回错误（已应用的不回滚，仅报告已应用数）
        返回：ToolResult，data 中包含 file/action 等信息
        """
        try:
            parsed = self.codex_parser.parse(patch_text)
        except ValidationError as e:
            return ToolResult(success=False, error=str(e))

        file_path = self.security.validate_write_path(parsed.file_path)

        lock = _get_lock(file_path)
        async with lock:
            if parsed.action == "add":
                if os.path.exists(file_path):
                    return ToolResult(success=False, error=f"目标已存在: {file_path}")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(self._diff_lines_to_file_lines(parsed.lines))
                return ToolResult(
                    success=True,
                    output=f"成功创建文件 {file_path}",
                    data={"file": file_path, "action": "add"},
                )

            if parsed.action == "delete":
                if not os.path.exists(file_path):
                    return ToolResult(success=False, error=f"目标不存在: {file_path}")
                if os.path.isdir(file_path):
                    return ToolResult(success=False, error=f"目标是目录: {file_path}")
                os.remove(file_path)
                return ToolResult(
                    success=True,
                    output=f"成功删除文件 {file_path}",
                    data={"file": file_path, "action": "delete"},
                )

            if parsed.action == "update":
                try:
                    with open(file_path, encoding="utf-8") as f:
                        original_lines = f.readlines()
                except FileNotFoundError:
                    return ToolResult(success=False, error=f"目标不存在: {file_path}")

                result_lines = original_lines[:]
                applied = 0
                for hunk in parsed.hunks:
                    success, error = self._apply_codex_hunk(result_lines, hunk)
                    if not success:
                        return ToolResult(
                            success=False, error=error, data={"file": file_path, "hunks_applied": applied}
                        )
                    applied += 1

                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(result_lines)
                return ToolResult(
                    success=True,
                    output=f"成功应用 {applied} 个修改到 {file_path}",
                    data={"file": file_path, "action": "update", "hunks_applied": applied},
                )

        return ToolResult(success=False, error="不支持的 patch 操作")

    async def _write(self, args: dict[str, Any]) -> ToolResult:
        """
        write 动作实现：整文件覆盖写入，主要用于创建新文件。

        入参：args 需包含 path、content（完整文件内容）
        逻辑：校验路径 -> 加文件锁 -> 若目录不存在则创建 -> 直接覆盖写入 content
        返回：成功时 output 提示文件已写入
        """
        path = self.security.validate_write_path(args["path"])
        content = args.get("content")
        if content is None:
            return ToolResult(success=False, error="缺少 content 参数")

        lock = _get_lock(path)
        async with lock:
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)

        return ToolResult(success=True, output=f"文件已写入: {path}")

    def _apply_hunks(self, original_lines: list[str], hunks: list) -> tuple:
        """
        将一组 Unified Diff hunk 逆序应用到原文件行列表上。

        入参：original_lines - 原文件按行切分的列表；hunks - DiffParser 解析出的 Hunk 列表
        逻辑：从后往前应用每个 hunk（避免前面的行号偏移影响后面 hunk 的定位），
            对每个 hunk 调用 _apply_hunk 尝试应用，统计成功/失败数量
        返回：(result_lines, applied, rejected) —— 应用后的行列表、成功数、失败（冲突）数
        """
        result_lines = original_lines[:]
        applied = 0
        rejected = 0
        for hunk in reversed(hunks):
            success = self._apply_hunk(result_lines, hunk)
            if success:
                applied += 1
            else:
                rejected += 1
        return result_lines, applied, rejected

    def _apply_hunk(self, lines: list[str], hunk: Any) -> bool:
        """
        将单个 Unified Diff hunk 应用到文件行列表（原地修改 lines）。

        入参：lines - 当前文件行列表（会被原地修改）；hunk - 待应用的 Hunk 对象
        逻辑：根据 hunk.lines 中的 +/-/空格前缀统计需删除的原行数（old_count）和
            替换后的新行内容（new_lines）-> 计算起始位置 start -> 逐行核对原文件
            对应位置内容是否与 hunk 期望的上下文/删除行一致（不一致则判定冲突）->
            核对通过后用 new_lines 替换 lines[start:start+old_count] 对应区间
        返回：True 表示应用成功；False 表示定位越界或内容不匹配（冲突），未修改 lines
        """
        old_count = 0
        new_lines: list[str] = []
        for line in hunk.lines:
            if line.startswith("-"):
                old_count += 1
            elif line.startswith("+"):
                new_lines.append(line[1:] + "\n")
            elif line.startswith(" "):
                old_count += 1
                new_lines.append(line[1:] + "\n")

        start = hunk.old_start - 1
        if old_count == 0 and hunk.old_start > 0:
            start = hunk.old_start
        if start < 0 and old_count == 0:
            start = 0
        elif start < 0 or start > len(lines):
            return False

        old_offset = 0
        for line in hunk.lines:
            if line.startswith("+"):
                continue
            idx = start + old_offset
            if idx >= len(lines):
                return False
            actual = lines[idx].rstrip("\n").rstrip("\r")
            expected = line[1:]
            if actual != expected:
                return False
            old_offset += 1

        try:
            if start + old_count <= len(lines):
                lines[start : start + old_count] = new_lines
                return True
            return False
        except Exception:
            return False

    def _apply_codex_hunk(self, lines: list[str], hunk_lines: list[str]) -> tuple[bool, str]:
        """
        将单个 Codex 风格 hunk 应用到文件行列表（原地修改 lines）。

        入参：lines - 当前文件行列表（会被原地修改）；hunk_lines - 该 hunk 的原始行
            （以空格/-/+ 开头，分别代表上下文/删除/新增）
        逻辑：拆分出 old_block（上下文+删除行，代表原文件应有的连续片段）和
            new_block（上下文+新增行，代表替换后的内容）-> 在 lines 中查找 old_block
            的唯一匹配位置（要求恰好一处，多处或零处均视为冲突）-> 用 new_block 替换该区间
        返回：(success, error_msg) —— 成功时 error_msg 为空字符串；
            失败原因包括缺少上下文、未匹配到、匹配到多处
        """
        old_block: list[str] = []
        new_block: list[str] = []
        for line in hunk_lines:
            if line.startswith(" "):
                old_block.append(line[1:] + "\n")
                new_block.append(line[1:] + "\n")
            elif line.startswith("-"):
                old_block.append(line[1:] + "\n")
            elif line.startswith("+"):
                new_block.append(line[1:] + "\n")

        if not old_block:
            return False, "hunk 缺少上下文或删除行"

        matches = []
        max_start = len(lines) - len(old_block)
        for start in range(max_start + 1):
            if lines[start : start + len(old_block)] == old_block:
                matches.append(start)

        if not matches:
            return False, "Patch 冲突: hunk 未匹配到原文件内容"
        if len(matches) > 1:
            return False, "Patch 冲突: hunk 匹配到多个位置，请增加上下文"

        start = matches[0]
        lines[start : start + len(old_block)] = new_block
        return True, ""

    def _diff_lines_to_file_lines(self, diff_lines: list[str]) -> list[str]:
        """将 Codex Add File 的 diff 行（每行前缀为 +）转换为真实文件行（去掉前缀、补回换行符）"""
        return [line[1:] + "\n" for line in diff_lines]

    def get_schema(self) -> dict[str, Any]:
        """
        返回工具的 JSON Schema，传递给 LLM 的 tools 参数。

        出参：dict，定义 action（枚举 str_replace/patch/write）、path 及各 action
            专属参数（old_string/new_string/replace_all、patch、content）。
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
                        "enum": ["str_replace", "patch", "write"],
                        "description": (
                            "Edit mode: str_replace=string replacement (recommended, supports fuzzy matching), "
                            "patch=apply diff patch, write=full write (only for creating new files)"
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": "File path (relative or absolute)",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "For str_replace: text to replace; empty string means append to file end or create new file",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "For str_replace: replacement text, must differ from old_string",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "default": False,
                        "description": "For str_replace: replace all occurrences (default: only first unique match)",
                    },
                    "patch": {
                        "type": "string",
                        "description": "For patch: patch content, supports Unified Diff and Codex-style patch",
                    },
                    "content": {
                        "type": "string",
                        "description": "For write: full file content",
                    },
                },
                "required": ["action", "path"],
            },
        }
