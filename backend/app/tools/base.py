from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolApprovalRequest(BaseModel):
    """工具审批请求"""

    approval_id: str
    tool_name: str
    summary: str
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str | None = None
    suggested_trust: dict[str, Any] | None = None


class ToolResult(BaseModel):
    """工具执行结果"""

    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None
    approval_required: bool = False
    approval: ToolApprovalRequest | None = None


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
