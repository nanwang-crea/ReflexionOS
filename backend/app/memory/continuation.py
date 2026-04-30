from __future__ import annotations

from uuid import uuid4

from app.llm.base import MessageRole
from app.models.conversation import Message, MessageType, StreamState


def build_continuation_artifact(
    *,
    session_id: str,
    turn_id: str,
    content_text: str,
    message_id: str | None = None,
    turn_message_index: int = 9999,
) -> Message:
    """
    Build the continuation artifact message envelope (Task 5) while leaving content generation
    to a single LLM-driven compression step (Task 6).

    The provided content_text SHOULD already be a compact handoff note.
    """
    content = (content_text or "").strip()

    return Message(
        id=message_id or f"msg-cont-{uuid4().hex[:8]}",
        session_id=session_id,
        turn_id=turn_id,
        run_id=None,
        turn_message_index=turn_message_index,
        role=MessageRole.SYSTEM,
        message_type=MessageType.SYSTEM_NOTICE,
        stream_state=StreamState.COMPLETED,
        display_mode="collapsed",
        content_text=content,
        payload_json={
            "kind": "continuation_artifact",
            "derived": True,
            "exclude_from_recall": True,
            "exclude_from_memory_promotion": True,
        },
    )
