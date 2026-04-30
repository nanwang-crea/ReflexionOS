import pytest

from app.execution.approval_store import PendingApprovalStore


def test_pending_approval_store_creates_and_reads_pending_approval():
    store = PendingApprovalStore()

    pending = store.create(
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=3,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={"summary": "Run tests"},
    )

    stored = store.get(pending.id)

    assert stored is not None
    assert stored.id == pending.id
    assert stored.status == "pending"
    assert stored.session_id == "session-1"
    assert stored.turn_id == "turn-1"
    assert stored.run_id == "run-1"
    assert stored.step_number == 3
    assert stored.tool_call_id == "call-1"
    assert stored.tool_name == "shell"
    assert stored.tool_arguments == {"command": "pytest -q"}
    assert stored.approval_payload == {"summary": "Run tests"}
    assert stored.created_at is not None
    assert stored.decided_at is None
    assert stored.decision is None


def test_pending_approval_store_can_create_with_explicit_approval_id():
    store = PendingApprovalStore()

    pending = store.create(
        approval_id="approval-explicit",
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=3,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={"summary": "Run tests"},
    )

    stored = store.get("approval-explicit")

    assert pending.id == "approval-explicit"
    assert stored is not None
    assert stored.id == "approval-explicit"


def test_pending_approval_store_deep_copies_nested_create_inputs():
    store = PendingApprovalStore()
    tool_arguments = {
        "command": "python script.py",
        "metadata": {"flags": ["--dry-run"]},
    }
    approval_payload = {
        "summary": "Run script",
        "risks": [{"kind": "shell", "reasons": ["executes command"]}],
    }

    pending = store.create(
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments=tool_arguments,
        approval_payload=approval_payload,
    )
    tool_arguments["metadata"]["flags"].append("--mutated")
    approval_payload["risks"][0]["reasons"].append("mutated")

    stored = store.get(pending.id)

    assert stored is not None
    assert stored.tool_arguments == {
        "command": "python script.py",
        "metadata": {"flags": ["--dry-run"]},
    }
    assert stored.approval_payload == {
        "summary": "Run script",
        "risks": [{"kind": "shell", "reasons": ["executes command"]}],
    }


def test_pending_approval_store_approves_pending_approval():
    store = PendingApprovalStore()
    pending = store.create(
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={},
    )

    approved = store.approve(pending.id, decision="allow_once")

    assert approved.status == "approved"
    assert approved.decision == "allow_once"
    assert approved.decided_at is not None
    assert store.get(pending.id).status == "approved"


def test_pending_approval_store_rejects_deny_decision_for_approve():
    store = PendingApprovalStore()
    pending = store.create(
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={},
    )

    with pytest.raises(ValueError):
        store.approve(pending.id, decision="deny")

    assert store.get(pending.id).status == "pending"
    assert store.get(pending.id).decision is None


def test_pending_approval_store_denies_pending_approval():
    store = PendingApprovalStore()
    pending = store.create(
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={},
    )

    denied = store.deny(pending.id)

    assert denied.status == "denied"
    assert denied.decision == "deny"
    assert denied.decided_at is not None
    assert store.get(pending.id).status == "denied"


def test_pending_approval_store_expires_pending_approvals_for_run_only():
    store = PendingApprovalStore()
    run_1_pending = store.create(
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={},
        approval_payload={},
    )
    run_1_approved = store.create(
        session_id="session-1",
        turn_id="turn-1",
        run_id="run-1",
        step_number=2,
        tool_call_id="call-2",
        tool_name="shell",
        tool_arguments={},
        approval_payload={},
    )
    run_2_pending = store.create(
        session_id="session-1",
        turn_id="turn-2",
        run_id="run-2",
        step_number=1,
        tool_call_id="call-3",
        tool_name="shell",
        tool_arguments={},
        approval_payload={},
    )
    store.approve(run_1_approved.id)

    expired = store.expire_for_run("run-1")

    assert [approval.id for approval in expired] == [run_1_pending.id]
    assert store.get(run_1_pending.id).status == "expired"
    assert store.get(run_1_approved.id).status == "approved"
    assert store.get(run_2_pending.id).status == "pending"
