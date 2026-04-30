import logging
import os
from typing import Any

from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult
from app.tools.diff_parser import CodexPatchParseError, CodexPatchParser, DiffParser, Hunk

logger = logging.getLogger(__name__)


class PatchTool(BaseTool):
    """Patch 工具 - 应用代码补丁"""

    def __init__(self, security: PathSecurity):
        self.security = security
        self.parser = DiffParser()
        self.codex_parser = CodexPatchParser()

    @property
    def name(self) -> str:
        return "patch"

    @property
    def description(self) -> str:
        return "应用单文件代码补丁，支持 Unified Diff 和 Codex-style patch"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """
        执行 Patch

        Args:
            args: 包含 patch 参数的字典

        Returns:
            ToolResult: 执行结果
        """
        patch_text = args.get("patch")

        if not patch_text:
            return ToolResult(success=False, error="缺少 patch 参数")

        try:
            if self.codex_parser.is_codex_style(patch_text):
                return await self._execute_codex_patch(patch_text)
            return await self._execute_unified_diff(patch_text)

        except Exception as e:
            logger.error("Patch 执行失败: %s", e)
            return ToolResult(success=False, error=str(e))

    async def _execute_unified_diff(self, patch_text: str) -> ToolResult:
        file_paths = self.parser.extract_file_paths(patch_text)
        unique_file_paths = list(dict.fromkeys(file_paths))
        if len(unique_file_paths) > 1:
            return ToolResult(
                success=False, error="Unified Diff 仅支持单文件 patch，请一次只修改一个文件"
            )

        hunks = self.parser.parse(patch_text)

        if not hunks:
            return ToolResult(success=False, error=self._describe_unified_parse_error(patch_text))

        # 提取文件路径
        file_path = self.parser.extract_file_path(patch_text)
        if not file_path:
            return ToolResult(
                success=False, error="无法从 Unified Diff 中提取文件路径，请包含 --- 和 +++ 文件头"
            )

        # 验证路径安全性
        file_path = self.security.validate_write_path(file_path)

        # 读取原文件
        try:
            with open(file_path, encoding="utf-8") as f:
                original_lines = f.readlines()
        except FileNotFoundError:
            logger.info("目标文件不存在,将创建新文件: %s", file_path)
            original_lines = []

        # 应用 Patch
        result_lines, applied, rejected = self._apply_hunks(original_lines, hunks)

        if rejected == 0:
            # 写入修改后的文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(result_lines)

            logger.info("成功应用 Patch: %s, %s 个 Hunk", file_path, applied)
            return ToolResult(
                success=True,
                output=f"成功应用 {applied} 个修改到 {file_path}",
                data={"file": file_path, "hunks_applied": applied, "hunks_rejected": rejected},
            )

        logger.warning("Patch 部分失败: %s 个 Hunk 被拒绝", rejected)
        return ToolResult(
            success=False,
            error=f"Patch 冲突: {rejected}/{len(hunks)} 个修改无法应用",
            data={"file": file_path, "hunks_applied": applied, "hunks_rejected": rejected},
        )

    async def _execute_codex_patch(self, patch_text: str) -> ToolResult:
        try:
            parsed = self.codex_parser.parse(patch_text)
        except CodexPatchParseError as e:
            return ToolResult(success=False, error=str(e))

        file_path = self.security.validate_write_path(parsed.file_path)

        if parsed.action == "add":
            if os.path.exists(file_path):
                return ToolResult(
                    success=False, error=f"Codex-style Add File 目标已存在: {file_path}"
                )

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(self._diff_lines_to_file_lines(parsed.lines))

            return ToolResult(
                success=True,
                output=f"成功创建文件 {file_path}",
                data={"file": file_path, "action": "add"},
            )

        if parsed.action == "delete":
            if not os.path.exists(file_path):
                return ToolResult(
                    success=False, error=f"Codex-style Delete File 目标不存在: {file_path}"
                )
            if os.path.isdir(file_path):
                return ToolResult(
                    success=False, error=f"Codex-style Delete File 目标是目录: {file_path}"
                )

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
                return ToolResult(
                    success=False, error=f"Codex-style Update File 目标不存在: {file_path}"
                )

            result_lines = original_lines[:]
            applied = 0
            for hunk in parsed.hunks:
                success, error = self._apply_codex_hunk(result_lines, hunk)
                if not success:
                    return ToolResult(
                        success=False,
                        error=error,
                        data={"file": file_path, "hunks_applied": applied},
                    )
                applied += 1

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(result_lines)

            return ToolResult(
                success=True,
                output=f"成功应用 {applied} 个 Codex-style 修改到 {file_path}",
                data={"file": file_path, "action": "update", "hunks_applied": applied},
            )

        return ToolResult(success=False, error=f"不支持的 Codex-style patch 操作: {parsed.action}")

    def _apply_hunks(self, original_lines: list[str], hunks: list[Hunk]) -> tuple:
        """
        应用所有 Hunk

        Args:
            original_lines: 原文件行列表
            hunks: Hunk 列表

        Returns:
            tuple: (结果行列表, 成功数, 失败数)
        """
        result_lines = original_lines[:]
        applied = 0
        rejected = 0

        # 从后往前应用,避免行号偏移
        for hunk in reversed(hunks):
            success = self._apply_hunk(result_lines, hunk)
            if success:
                applied += 1
            else:
                rejected += 1

        return result_lines, applied, rejected

    def _diff_lines_to_file_lines(self, diff_lines: list[str]) -> list[str]:
        return [line[1:] + "\n" for line in diff_lines]

    def _apply_hunk(self, lines: list[str], hunk: Hunk) -> bool:
        """
        应用单个 Hunk

        Args:
            lines: 文件行列表 (会被修改)
            hunk: 要应用的 Hunk

        Returns:
            bool: 是否成功
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

        start = hunk.old_start - 1  # 转为 0-based
        if old_count == 0 and hunk.old_start > 0:
            start = hunk.old_start

        # 新文件创建: old_start=0 → start=-1, old_count=0
        if start < 0 and old_count == 0:
            start = 0
        elif start < 0 or start > len(lines):
            return False

        # 校验上下文行和删除行与实际文件内容匹配
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
                logger.warning(
                    "Hunk 原文件内容不匹配: 行 %d 期望 %r, 实际 %r",
                    hunk.old_start + old_offset,
                    expected,
                    actual,
                )
                return False
            old_offset += 1

        # 执行替换
        try:
            if start + old_count <= len(lines):
                lines[start : start + old_count] = new_lines
                return True
            return False
        except Exception as e:
            logger.error("应用 Hunk 失败: %s", e)
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
            return (False, "Codex-style Update File 的 hunk 缺少上下文或删除行，无法安全定位")

        matches = []
        max_start = len(lines) - len(old_block)
        for start in range(max_start + 1):
            if lines[start : start + len(old_block)] == old_block:
                matches.append(start)

        if not matches:
            return False, "Patch 冲突: Codex-style hunk 未匹配到原文件内容"
        if len(matches) > 1:
            return False, "Patch 冲突: Codex-style hunk 匹配到多个位置，请增加上下文"

        start = matches[0]
        lines[start : start + len(old_block)] = new_block
        return True, ""

    def _describe_unified_parse_error(self, patch_text: str) -> str:
        if "*** Begin Patch" in patch_text:
            return (
                "检测到 Codex-style patch，但格式不完整；"
                "请使用 *** Begin Patch / *** Update File / @@ / *** End Patch"
            )
        if "--- " in patch_text or "+++ " in patch_text:
            if "@@" not in patch_text:
                return "无法解析 Unified Diff：缺少 @@ hunk header"
            return "无法解析 Unified Diff：hunk header 格式无效，应类似 @@ -1,2 +1,2 @@"
        if "@@" in patch_text:
            return "无法解析 Unified Diff：缺少 --- 和 +++ 文件头"
        return "无法解析 Diff 格式：支持 Unified Diff 或 Codex-style patch"

    def get_schema(self) -> dict[str, Any]:
        """获取工具的 JSON Schema"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": (
                            "补丁内容。支持两种单文件格式："
                            "1) Unified Diff，必须包含 ---、+++ 和 @@ -old,count +new,count @@；"
                            "2) Codex-style patch，必须包含 *** Begin Patch、"
                            "*** Add/Update/Delete File、@@、*** End Patch。"
                            "不要一次传入多文件 diff。"
                        ),
                    }
                },
                "required": ["patch"],
            },
        }
