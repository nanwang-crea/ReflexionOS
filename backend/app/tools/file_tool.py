import os
import aiofiles
from typing import Dict, Any, List
from app.tools.base import BaseTool, ToolResult
from app.security.path_security import PathSecurity
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class FileTool(BaseTool):
    """文件操作工具"""
    
    def __init__(self, security: PathSecurity):
        self.security = security
    
    @property
    def name(self) -> str:
        return "file"
    
    @property
    def description(self) -> str:
        return "文件读写和目录操作工具"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行文件操作
        
        Args:
            args: 包含 action 和相关参数的字典
            
        Returns:
            ToolResult: 执行结果
        """
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
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
                
        except Exception as e:
            logger.error(f"文件操作失败: {str(e)}")
            return ToolResult(success=False, error=str(e))
    
    async def _read_file(self, args: Dict[str, Any]) -> ToolResult:
        """读取文件内容"""
        path = self.security.validate_path(args["path"])
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        
        if os.path.getsize(path) > settings.max_file_size:
            return ToolResult(success=False, error="文件大小超过限制")
        
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            content = await f.read()
        
        logger.info(f"成功读取文件: {path}")
        return ToolResult(
            success=True,
            data={"content": content, "path": path}
        )
    
    async def _write_file(self, args: Dict[str, Any]) -> ToolResult:
        """写入文件内容"""
        path = self.security.validate_write_path(args["path"])
        content = args["content"]
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        async with aiofiles.open(path, mode='w', encoding='utf-8') as f:
            await f.write(content)
        
        logger.info(f"成功写入文件: {path}")
        return ToolResult(success=True, output=f"文件已写入: {path}")
    
    async def _list_directory(self, args: Dict[str, Any]) -> ToolResult:
        """列出目录内容"""
        path = self.security.validate_path(args["path"])
        
        if not os.path.isdir(path):
            return ToolResult(success=False, error=f"不是目录: {path}")
        
        files: List[Dict[str, str]] = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            files.append({
                "name": item,
                "type": "directory" if os.path.isdir(item_path) else "file"
            })
        
        logger.info(f"成功列出目录: {path}, 共 {len(files)} 项")
        return ToolResult(success=True, data={"files": files, "path": path})
    
    async def _delete_file(self, args: Dict[str, Any]) -> ToolResult:
        """删除文件"""
        path = self.security.validate_write_path(args["path"])
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        
        os.remove(path)
        logger.info(f"成功删除文件: {path}")
        return ToolResult(success=True, output=f"文件已删除: {path}")
