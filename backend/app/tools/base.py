import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.security.path_security import ExternalPathError


class ToolApprovalRequest(BaseModel):
    approval_id: str
    tool_name: str
    summary: str
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str | None = None
    suggested_trust: dict[str, Any] | None = None


class ToolResult(BaseModel):
    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None
    approval_required: bool = False
    approval: ToolApprovalRequest | None = None


def _external_path_approval(tool_name: str, exc: ExternalPathError) -> ToolResult:
    import uuid
    parent = os.path.dirname(exc.requested_path)
    return ToolResult(
        success=False,
        approval_required=True,
        approval=ToolApprovalRequest(
            approval_id=f"approval-{uuid.uuid4().hex[:12]}",
            tool_name=tool_name,
            summary=f"访问项目外路径: {exc.requested_path}",
            reasons=["路径不在项目允许范围内"],
            risks=["可能读取或暴露项目外敏感文件"],
            payload={
                "path": exc.requested_path,
                "allowed_paths": exc.allowed_paths,
                "access_type": "external_path_read",
                "suggested_prefix_rule": [parent + os.sep + "*"],
            },
            suggested_trust={"prefix": [parent + os.sep + "*"]},
        ),
    )


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
