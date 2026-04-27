import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ExecutionStep(BaseModel):
    id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    step_number: int
    tool: str
    args: dict
    status: StepStatus = StepStatus.PENDING
    output: str | None = None
    error: str | None = None
    duration: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ExecutionBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task: str
    provider_id: str | None = None
    model_id: str | None = None


class Execution(ExecutionBase):
    model_config = ConfigDict(
        protected_namespaces=(),
        from_attributes=True,
    )

    project_id: str = ""
    session_id: str = ""
    project_path: str = ""
    id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:8]}")
    status: ExecutionStatus = ExecutionStatus.PENDING
    steps: list[ExecutionStep] = []
    result: str | None = None
    total_duration: float | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
