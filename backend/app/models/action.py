from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    FINISH = "finish"


class Action(BaseModel):
    type: ActionType
    thought: Optional[str] = None
    tool: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ActionResult(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
