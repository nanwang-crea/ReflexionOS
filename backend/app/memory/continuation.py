from __future__ import annotations

from uuid import uuid4

from app.models.conversation import Message, MessageType, StreamState


def _summarize_messages(messages: list[Message], *, limit: int = 20) -> str:
    """
    Minimal, deterministic "summary" built directly from message contents.

    Task 5 scope: keep it simple and message-centric; no external memory store, no LLM calls.
    """
    if not messages:
        return ""

    # Keep newest context, but preserve original ordering.
    sliced = messages[-limit:]
    parts: list[str] = []
    for message in sliced:
        text = (message.content_text or "").strip()
        if not text and isinstance(message.payload_json, dict) and message.payload_json:
            # Tool traces often store structured payload; keep a compact hint.
            tool_name = message.payload_json.get("tool_name")
            output = message.payload_json.get("output")
            if tool_name:
                text = f"tool_name={tool_name}"
            if output:
                output_str = str(output).strip()
                if output_str:
                    text = "\n".join([text, f"output={output_str}"]) if text else f"output={output_str}"
        if text:
            parts.append(text)
    return "\n".join(parts)


def summarize_confirmed_facts(messages: list[Message]) -> str:
    # Placeholder heuristic: include the key textual context so the artifact is self-contained.
    return _summarize_messages(messages)


def summarize_open_items(messages: list[Message]) -> str:
    # Keep Task 5 minimal: we don't yet have structured "open items", so reuse context.
    return _summarize_messages(messages)


def summarize_next_action(messages: list[Message]) -> str:
    # Keep Task 5 minimal: surface the latest assistant text if available.
    for message in reversed(messages):
        if message.message_type == MessageType.ASSISTANT_MESSAGE and message.content_text.strip():
            return message.content_text.strip()
    return ""


def build_continuation_artifact(
    *,
    session_id: str,
    turn_id: str,
    messages: list[Message],
    active_goal: str,
) -> Message:
    content = "\n".join(
        [
            "当前目标: " + (active_goal or ""),
            "已确认事实: " + summarize_confirmed_facts(messages),
            "未解决点: " + summarize_open_items(messages),
            "下一步建议: " + summarize_next_action(messages),
        ]
    ).strip()

    return Message(
        id=f"msg-cont-{uuid4().hex[:8]}",
        session_id=session_id,
        turn_id=turn_id,
        run_id=None,
        turn_message_index=9999,
        role="system",
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

