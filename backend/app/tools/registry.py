from typing import Dict, List, Optional
from app.tools.base import BaseTool
import logging

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """工具未找到错误"""
    pass


class ToolRegistry:
    """工具注册和管理中心"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        logger.info("工具注册中心初始化完成")
    
    def register(self, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self.tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def unregister(self, name: str) -> None:
        """
        注销工具
        
        Args:
            name: 工具名称
        """
        if name in self.tools:
            del self.tools[name]
            logger.info(f"注销工具: {name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            Optional[BaseTool]: 工具实例,如果不存在返回 None
        """
        return self.tools.get(name)
    
    def get_tool_schema(self, name: str) -> Dict:
        """
        获取工具的 JSON Schema
        
        Args:
            name: 工具名称
            
        Returns:
            Dict: 工具 Schema
        """
        tool = self.get(name)
        if not tool:
            raise ToolNotFoundError(f"工具不存在: {name}")
        return tool.get_schema()
    
    def get_all_schemas(self) -> List[Dict]:
        """
        获取所有工具的 Schema
        
        Returns:
            List[Dict]: 所有工具的 Schema 列表
        """
        return [tool.get_schema() for tool in self.tools.values()]
    
    def list_tools(self) -> List[str]:
        """
        列出所有注册的工具名称
        
        Returns:
            List[str]: 工具名称列表
        """
        return list(self.tools.keys())
