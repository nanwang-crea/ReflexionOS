import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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
