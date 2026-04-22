from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """工具调用"""
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class Action(BaseModel):
    """Agent 动作 - OpenAI Assistant 风格"""
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    thought: str | None = None
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
    
    @property
    def is_finish(self) -> bool:
        """没有工具调用且没有待执行的任务时视为完成"""
        return not self.has_tool_calls and bool(self.content)


class ActionResult(BaseModel):
    success: bool
    output: str | None = None
    error: str | None = None
    duration: float | None = None
