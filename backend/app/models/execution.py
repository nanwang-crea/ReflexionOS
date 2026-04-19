from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
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
    output: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ExecutionBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str
    task: str
    provider_id: Optional[str] = None
    model_id: Optional[str] = None


class ExecutionCreate(ExecutionBase):
    pass


class Execution(ExecutionBase):
    id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:8]}")
    status: ExecutionStatus = ExecutionStatus.PENDING
    steps: List[ExecutionStep] = []
    result: Optional[str] = None
    total_duration: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
