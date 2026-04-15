from typing import Dict, Any, List
from app.tools.base import BaseTool, ToolResult
from app.security.path_security import PathSecurity
from app.tools.diff_parser import DiffParser, Hunk
import logging

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
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
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
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_lines = f.readlines()
            except FileNotFoundError:
                logger.info(f"目标文件不存在,将创建新文件: {file_path}")
                original_lines = []
            
            # 应用 Patch
            result_lines, applied, rejected = self._apply_hunks(original_lines, hunks)
            
            if rejected == 0:
                # 写入修改后的文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(result_lines)
                
                logger.info(f"成功应用 Patch: {file_path}, {applied} 个 Hunk")
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
                logger.warning(f"Patch 部分失败: {rejected} 个 Hunk 被拒绝")
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
            logger.error(f"Patch 执行失败: {str(e)}")
            return ToolResult(success=False, error=str(e))
    
    def _apply_hunks(self, original_lines: List[str], hunks: List[Hunk]) -> tuple:
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
    
    def _apply_hunk(self, lines: List[str], hunk: Hunk) -> bool:
        """
        应用单个 Hunk
        
        Args:
            lines: 文件行列表 (会被修改)
            hunk: 要应用的 Hunk
            
        Returns:
            bool: 是否成功
        """
        # 计算删除和新增的行
        delete_count = 0
        new_lines = []
        
        for line in hunk.lines:
            if line.startswith('-'):
                delete_count += 1
            elif line.startswith('+'):
                new_lines.append(line[1:] + '\n')
            elif line.startswith(' '):
                # 上下文行,不计入删除
                pass
        
        # 计算插入位置
        start = hunk.old_start - 1  # 转为 0-based
        
        # 边界检查
        if start < 0:
            start = 0
        if start > len(lines):
            start = len(lines)
        
        # 执行替换
        try:
            # 确保有足够的行可以删除
            if start + delete_count <= len(lines):
                lines[start:start + delete_count] = new_lines
                return True
            else:
                # 行数不够,可能是新增文件
                lines.extend(new_lines)
                return True
        except Exception as e:
            logger.error(f"应用 Hunk 失败: {e}")
            return False
    
    def get_schema(self) -> Dict[str, Any]:
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
