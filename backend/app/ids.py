from uuid import uuid4


def new_event_id() -> str:
    return f"evt-{uuid4().hex[:8]}"


def new_message_id() -> str:
    return f"msg-{uuid4().hex[:8]}"


def new_run_id() -> str:
    return f"run-{uuid4().hex[:8]}"


def new_turn_id() -> str:
    return f"turn-{uuid4().hex[:8]}"


def new_session_id() -> str:
    return f"session-{uuid4().hex[:8]}"


def new_approval_id() -> str:
    return f"approval-{uuid4().hex[:12]}"
