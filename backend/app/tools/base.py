from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    """工具执行结果"""

    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None


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
    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """
        执行工具

        Args:
            args: 工具参数

        Returns:
            ToolResult: 执行结果
        """
        pass

    def get_schema(self) -> dict[str, Any]:
        """
        获取工具的 JSON Schema（统一格式）

        Returns:
            Dict containing name, description, parameters
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
