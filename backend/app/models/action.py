from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum


class ToolCall(BaseModel):
    """工具调用"""
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class Action(BaseModel):
    """Agent 动作 - OpenAI Assistant 风格"""
    content: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    thought: Optional[str] = None
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
    
    @property
    def is_finish(self) -> bool:
        """没有工具调用且没有待执行的任务时视为完成"""
        return not self.has_tool_calls and bool(self.content)


class ActionResult(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
