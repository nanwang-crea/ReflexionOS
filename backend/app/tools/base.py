"""
工具体系基础定义模块。

提供所有 Agent 工具共用的基础类型：
- ToolApprovalRequest / ToolResult：工具执行结果与审批请求的统一数据结构；
- BaseTool：所有具体工具（文件编辑、grep、shell、浏览器等）必须继承的抽象基类，
  规定了工具的 name/description/execute/get_schema 接口。
"""
import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.security.path_security import ExternalPathError


class ToolApprovalRequest(BaseModel):
    """当工具需要访问受限资源（如项目外路径）时，返回给上层用于人工审批的请求信息"""
    approval_id: str
    tool_name: str
    summary: str
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str | None = None
    suggested_trust: dict[str, Any] | None = None


class ToolResult(BaseModel):
    """所有工具 execute() 方法的统一返回结构：成功/失败、输出内容、错误信息及可选的审批请求"""
    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None
    approval_required: bool = False
    approval: ToolApprovalRequest | None = None


def _external_path_approval(tool_name: str, exc: ExternalPathError) -> ToolResult:
    """
    将“访问了项目外部路径”的异常转换为需要用户审批的 ToolResult。

    输入参数：
        tool_name: 触发该异常的工具名称
        exc: 路径安全校验抛出的 ExternalPathError，携带请求路径与允许路径列表

    工作流程：生成唯一 approval_id，取请求路径的父目录作为建议的信任前缀规则，
    组装成 approval_required=True 的失败结果，交由上层展示给用户确认。

    返回值：success=False 且携带 approval 信息的 ToolResult
    """
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
