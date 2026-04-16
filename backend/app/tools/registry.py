from typing import Dict, List, Optional
from app.tools.base import BaseTool
from app.llm.base import LLMToolDefinition
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
        """注册工具"""
        self.tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def unregister(self, name: str) -> None:
        """注销工具"""
        if name in self.tools:
            del self.tools[name]
            logger.info(f"注销工具: {name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self.tools.get(name)
    
    def get_tool_schema(self, name: str) -> Dict:
        """获取工具的 JSON Schema"""
        tool = self.get(name)
        if not tool:
            raise ToolNotFoundError(f"工具不存在: {name}")
        return tool.get_schema()
    
    def get_all_schemas(self) -> List[Dict]:
        """获取所有工具的 Schema"""
        return [tool.get_schema() for tool in self.tools.values()]
    
    def get_tool_definitions(self) -> List[LLMToolDefinition]:
        """
        获取所有工具的定义（统一格式）
        
        用于传递给 LLM 的 tools 参数
        
        Returns:
            List[LLMToolDefinition]: 工具定义列表
        """
        definitions = []
        for tool in self.tools.values():
            schema = tool.get_schema()
            definitions.append(LLMToolDefinition(
                name=schema["name"],
                description=schema["description"],
                parameters=schema.get("parameters", {})
            ))
        return definitions
    
    def list_tools(self) -> List[str]:
        """列出所有注册的工具名称"""
        return list(self.tools.keys())
