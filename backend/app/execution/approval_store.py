import uuid
from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field


ApprovalStatus = Literal["pending", "approved", "denied", "expired", "stale"]
ApprovalDecision = Literal["allow_once", "deny", "trust_and_allow"]
AllowApprovalDecision = Literal["allow_once", "trust_and_allow"]


class PendingToolApproval(BaseModel):
    id: str = Field(default_factory=lambda: f"approval-{uuid.uuid4().hex[:12]}")
    session_id: str
    turn_id: str
    run_id: str
    step_number: int
    tool_call_id: str
    tool_name: str
    tool_arguments: dict
    approval_payload: dict
    status: ApprovalStatus = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    decided_at: datetime | None = None
    decision: ApprovalDecision | None = None


class PendingApprovalStore:
    def __init__(self) -> None:
        self._approvals: dict[str, PendingToolApproval] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        approval_id: str | None = None,
        session_id: str,
        turn_id: str,
        run_id: str,
        step_number: int,
        tool_call_id: str,
        tool_name: str,
        tool_arguments: dict,
        approval_payload: dict,
    ) -> PendingToolApproval:
        with self._lock:
            pending_data = {
                "session_id": session_id,
                "turn_id": turn_id,
                "run_id": run_id,
                "step_number": step_number,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_arguments": deepcopy(tool_arguments),
                "approval_payload": deepcopy(approval_payload),
            }
            if approval_id is not None:
                pending_data["id"] = approval_id
            pending = PendingToolApproval(**pending_data)
            self._approvals[pending.id] = pending
            return pending.model_copy(deep=True)

    def get(self, approval_id: str) -> PendingToolApproval | None:
        with self._lock:
            pending = self._approvals.get(approval_id)
            if pending is None:
                return None
            return pending.model_copy(deep=True)

    def approve(
        self, approval_id: str, *, decision: AllowApprovalDecision = "allow_once"
    ) -> PendingToolApproval:
        if decision == "deny":
            raise ValueError("approve decision cannot be deny")
        return self._decide(approval_id, status="approved", decision=decision)

    def deny(self, approval_id: str) -> PendingToolApproval:
        return self._decide(approval_id, status="denied", decision="deny")

    def expire_for_run(self, run_id: str) -> list[PendingToolApproval]:
        expired: list[PendingToolApproval] = []
        with self._lock:
            for approval_id, pending in list(self._approvals.items()):
                if pending.run_id != run_id or pending.status != "pending":
                    continue
                updated = pending.model_copy(
                    update={"status": "expired", "decided_at": datetime.now()}
                )
                self._approvals[approval_id] = updated
                expired.append(updated.model_copy(deep=True))
        return expired

    def _decide(
        self,
        approval_id: str,
        *,
        status: Literal["approved", "denied"],
        decision: ApprovalDecision,
    ) -> PendingToolApproval:
        with self._lock:
            pending = self._approvals.get(approval_id)
            if pending is None:
                raise KeyError(f"approval not found: {approval_id}")
            if pending.status != "pending":
                raise ValueError(f"approval is not pending: {approval_id}")
            updated = pending.model_copy(
                update={
                    "status": status,
                    "decision": decision,
                    "decided_at": datetime.now(),
                }
            )
            self._approvals[approval_id] = updated
            return updated.model_copy(deep=True)
