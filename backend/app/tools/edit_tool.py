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

_file_locks: dict[str, asyncio.Lock] = {}


def _get_lock(path: str) -> asyncio.Lock:
    if path not in _file_locks:
        _file_locks[path] = asyncio.Lock()
    return _file_locks[path]


def _detect_line_ending(content: str) -> str:
    if "\r\n" in content:
        return "\r\n"
    return "\n"


def _detect_line_ending_from_bytes(raw: bytes) -> str:
    if b"\r\n" in raw:
        return "\r\n"
    return "\n"


def _normalize_to_lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def _convert_line_ending(text: str, ending: str) -> str:
    if ending == "\r\n":
        return text.replace("\n", "\r\n")
    return text


class EditTool(BaseTool):
    def __init__(self, security: PathSecurity):
        self.security = security
        self.parser = DiffParser()
        self.codex_parser = CodexPatchParser()

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "文件编辑工具。推荐使用 str_replace 进行精确或模糊替换；"
            "patch 用于复杂多行 diff 修改；write 仅用于创建新文件。"
        )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
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
        path = self.security.validate_write_path(args["path"])
        old_string = args.get("old_string", None)
        new_string = args.get("new_string", None)

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

            raw_bytes = await asyncio.to_thread(lambda: open(path, "rb").read())
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

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(result)

        return ToolResult(
            success=True,
            output=f"成功替换 {path}",
            data={"file": path, "action": "str_replace", "replace_all": replace_all},
        )

    async def _append_or_create(self, path: str, new_string: str) -> ToolResult:
        lock = _get_lock(path)
        async with lock:
            return await self._append_or_create_locked(path, new_string)

    async def _append_or_create_locked(self, path: str, new_string: str) -> ToolResult:
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        if os.path.exists(path):
            raw_bytes = await asyncio.to_thread(lambda: open(path, "rb").read())
            line_ending = _detect_line_ending_from_bytes(raw_bytes)
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
            normalized_new = _normalize_to_lf(new_string)
            if not content.endswith("\n"):
                content += line_ending
            content += _convert_line_ending(normalized_new, line_ending)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
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
        patch_text = args.get("patch")
        if not patch_text:
            return ToolResult(success=False, error="缺少 patch 参数")
        if self.codex_parser.is_codex_style(patch_text):
            return await self._execute_codex_patch(patch_text)
        return await self._execute_unified_diff(patch_text)

    async def _execute_unified_diff(self, patch_text: str) -> ToolResult:
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
        return [line[1:] + "\n" for line in diff_lines]

    def get_schema(self) -> dict[str, Any]:
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
                            "编辑模式：str_replace=字符串替换（推荐，支持模糊匹配）、"
                            "patch=应用diff补丁、write=全量写入（仅创建新文件）"
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对或绝对）",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "str_replace 使用：要替换的文本；空字符串表示追加到文件末尾或创建新文件",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "str_replace 使用：替换后的文本，必须与 old_string 不同",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "default": False,
                        "description": "str_replace 使用：替换所有出现位置（默认只替换第一个唯一匹配）",
                    },
                    "patch": {
                        "type": "string",
                        "description": "patch 使用：补丁内容，支持 Unified Diff 和 Codex-style patch",
                    },
                    "content": {
                        "type": "string",
                        "description": "write 使用：文件完整内容",
                    },
                },
                "required": ["action", "path"],
            },
        }
