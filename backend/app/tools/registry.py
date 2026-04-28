import logging

from app.llm.base import LLMToolDefinition
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """工具未找到错误"""
    pass


class ToolRegistry:
    """工具注册和管理中心"""
    
    def __init__(self):
        self.tools: dict[str, BaseTool] = {}
        logger.info("工具注册中心初始化完成")
    
    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self.tools[tool.name] = tool
        logger.info("注册工具: %s", tool.name)
    
    def unregister(self, name: str) -> None:
        """注销工具"""
        if name in self.tools:
            del self.tools[name]
            logger.info("注销工具: %s", name)
    
    def get(self, name: str) -> BaseTool | None:
        """获取工具"""
        return self.tools.get(name)
    
    def get_tool_schema(self, name: str) -> dict:
        """获取工具的 JSON Schema"""
        tool = self.get(name)
        if not tool:
            raise ToolNotFoundError(f"工具不存在: {name}")
        return tool.get_schema()
    
    def get_all_schemas(self) -> list[dict]:
        """获取所有工具的 Schema"""
        return [tool.get_schema() for tool in self.tools.values()]
    
    def get_tool_definitions(self) -> list[LLMToolDefinition]:
        """
        获取所有工具的定义（统一格式）
        
        用于传递给 LLM 的 tools 参数
        
        Returns:
            List[LLMToolDefinition]: 工具定义列表
        """
        definitions = []
        for tool in self.tools.values():
            schema = tool.get_schema()
            parameters = schema.get("parameters") or schema.get("input_schema", {})
            definitions.append(LLMToolDefinition(
                name=schema["name"],
                description=schema["description"],
                parameters=parameters
            ))
        return definitions
    
    def list_tools(self) -> list[str]:
        """列出所有注册的工具名称"""
        return list(self.tools.keys())

    def register_if_missing(self, tool: BaseTool) -> bool:
        """
        注册工具（若同名工具未注册）。

        Returns:
            bool: True 表示完成注册；False 表示已存在同名工具，未覆盖。
        """
        if tool.name in self.tools:
            return False
        self.register(tool)
        return True
