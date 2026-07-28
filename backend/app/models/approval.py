from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.ids import new_approval_id as _new_approval_id

ApprovalStatus = Literal["pending", "approved", "denied", "expired", "stale"]
ApprovalDecision = Literal["allow_once", "deny", "trust_and_allow"]
AllowApprovalDecision = Literal["allow_once", "trust_and_allow"]


class PendingToolApproval(BaseModel):
    id: str = Field(default_factory=_new_approval_id)
    session_id: str
    turn_id: str
    run_id: str
    step_number: int
    tool_call_id: str
    tool_call_metric_id: str | None = None
    invocation_id: str | None = None
    tool_started_at: datetime | None = None
    tool_name: str
    tool_arguments: dict
    approval_payload: dict
    status: ApprovalStatus = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    decided_at: datetime | None = None
    decision: ApprovalDecision | None = None
