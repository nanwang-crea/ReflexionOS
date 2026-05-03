import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.llm.base import LLMResponse


class LoopStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    SUCCESS = "success"
    FAILED = "failed"


class LoopStep(BaseModel):
    id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    step_number: int
    tool: str
    tool_call_id: str | None = None
    approval_id: str | None = None
    args: dict
    status: StepStatus = StepStatus.PENDING
    output: str | None = None
    error: str | None = None
    duration: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class LoopResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(default_factory=lambda: f"loop-{uuid.uuid4().hex[:8]}")
    task: str
    status: LoopStatus = LoopStatus.PENDING
    steps: list[LoopStep] = []
    result: str | None = None
    total_duration: float | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class LoopPhase(str, Enum):
    """状态机阶段 — 继承 str 保持与现有字符串比较兼容"""

    PLANNING = "planning"
    TOOL_EXECUTION = "tool_execution"
    ERROR_RECOVERY = "error_recovery"
    FINAL_SUMMARY = "final_summary"
    DONE = "done"


@dataclass
class RuntimeState:
    """单次 run 的可变状态快照 — handler 只操作这个对象"""

    phase: LoopPhase = LoopPhase.PLANNING
    step_num: int = 0
    turn_retries: int = 0
    consecutive_failures: int = 0
    has_executed_tools: bool = False
    response: LLMResponse | None = None
    approval_resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_result: dict | None = None
