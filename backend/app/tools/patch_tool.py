import logging
from typing import Any

from app.security.path_security import PathSecurity
from app.tools.base import BaseTool, ToolResult
from app.tools.diff_parser import DiffParser, Hunk

logger = logging.getLogger(__name__)


class PatchTool(BaseTool):
    """Patch 工具 - 应用 Unified Diff 格式的代码补丁"""
    
    def __init__(self, security: PathSecurity):
        self.security = security
        self.parser = DiffParser()
    
    @property
    def name(self) -> str:
        return "patch"
    
    @property
    def description(self) -> str:
        return "应用 Unified Diff 格式的代码补丁,进行精确的代码修改"
    
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
            # 解析 diff
            hunks = self.parser.parse(patch_text)
            
            if not hunks:
                return ToolResult(success=False, error="无法解析 Diff 格式,未找到有效的 Hunk")
            
            # 提取文件路径
            file_path = self.parser.extract_file_path(patch_text)
            if not file_path:
                return ToolResult(success=False, error="无法从 Diff 中提取文件路径")
            
            # 验证路径安全性
            file_path = self.security.validate_write_path(file_path)
            
            # 读取原文件
            try:
                with open(file_path, encoding='utf-8') as f:
                    original_lines = f.readlines()
            except FileNotFoundError:
                logger.info("目标文件不存在,将创建新文件: %s", file_path)
                original_lines = []
            
            # 应用 Patch
            result_lines, applied, rejected = self._apply_hunks(original_lines, hunks)
            
            if rejected == 0:
                # 写入修改后的文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(result_lines)
                
                logger.info("成功应用 Patch: %s, %s 个 Hunk", file_path, applied)
                return ToolResult(
                    success=True,
                    output=f"成功应用 {applied} 个修改到 {file_path}",
                    data={
                        "file": file_path,
                        "hunks_applied": applied,
                        "hunks_rejected": rejected
                    }
                )
            else:
                logger.warning("Patch 部分失败: %s 个 Hunk 被拒绝", rejected)
                return ToolResult(
                    success=False,
                    error=f"Patch 冲突: {rejected}/{len(hunks)} 个修改无法应用",
                    data={
                        "file": file_path,
                        "hunks_applied": applied,
                        "hunks_rejected": rejected
                    }
                )
        
        except Exception as e:
            logger.error("Patch 执行失败: %s", e)
            return ToolResult(success=False, error=str(e))
    
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
            if line.startswith('-'):
                old_count += 1
            elif line.startswith('+'):
                new_lines.append(line[1:] + '\n')
            elif line.startswith(' '):
                old_count += 1
                new_lines.append(line[1:] + '\n')

        start = hunk.old_start - 1  # 转为 0-based

        # 新文件创建: old_start=0 → start=-1, old_count=0
        if start < 0 and old_count == 0:
            start = 0
        elif start < 0 or start > len(lines):
            return False

        # 校验上下文行与实际文件内容匹配
        for i, line in enumerate(hunk.lines):
            if not line.startswith(' '):
                continue
            offset = sum(
                1 for l in hunk.lines[:i] if l.startswith('-') or l.startswith(' ')
            )
            idx = start + offset
            if idx >= len(lines):
                return False
            actual = lines[idx].rstrip('\n').rstrip('\r')
            expected = line[1:]
            if actual != expected:
                logger.warning(
                    "Hunk 上下文不匹配: 行 %d 期望 %r, 实际 %r",
                    hunk.old_start + offset,
                    expected,
                    actual,
                )
                return False

        # 执行替换
        try:
            if start + old_count <= len(lines):
                lines[start:start + old_count] = new_lines
                return True
            else:
                lines.extend(new_lines)
                return True
        except Exception as e:
            logger.error("应用 Hunk 失败: %s", e)
            return False
    
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
                        "description": "Unified Diff 格式的补丁内容"
                    }
                },
                "required": ["patch"]
            }
        }
