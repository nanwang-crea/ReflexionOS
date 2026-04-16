from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Dict, Optional


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class BaseTool(ABC):
    """工具基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
    
    @abstractmethod
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行工具
        
        Args:
            args: 工具参数
            
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具的 JSON Schema（统一格式）
        
        Returns:
            Dict containing name, description, parameters
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        获取工具定义（用于 LLM tools 参数）
        
        这是统一格式，各 Provider Adapter 负责转换为自己需要的格式
        """
        return self.get_schema()
