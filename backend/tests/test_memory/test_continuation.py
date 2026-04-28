from app.memory.continuation import build_continuation_artifact
from app.models.conversation import Message, MessageType, StreamState


def build_message(**overrides):
    payload = {
        "id": "msg-1",
        "session_id": "session-1",
        "turn_id": "turn-1",
        "run_id": "run-1",
        "turn_message_index": 1,
        "role": "assistant",
        "message_type": MessageType.ASSISTANT_MESSAGE,
        "stream_state": StreamState.COMPLETED,
        "display_mode": "default",
        "content_text": "hello",
        "payload_json": {},
    }
    payload.update(overrides)
    return Message(**payload)


def test_build_continuation_artifact_from_messages():
    artifact = build_continuation_artifact(
        session_id="session-1",
        turn_id="turn-1",
        messages=[
            build_message(
                id="msg-user-1",
                role="user",
                message_type=MessageType.USER_MESSAGE,
                content_text="继续设计 memory 系统",
            ),
            build_message(
                id="msg-assistant-1",
                role="assistant",
                message_type=MessageType.ASSISTANT_MESSAGE,
                content_text="先把 runtime 三层收敛",
            ),
            build_message(
                id="msg-tool-1",
                role="tool",
                message_type=MessageType.TOOL_TRACE,
                content_text="",
                payload_json={
                    "tool_name": "shell",
                    "arguments": {"cmd": "rg memory"},
                    "success": True,
                    "output": "docs/spec.md",
                },
            ),
        ],
        active_goal="把 message-centric 设计写清楚",
    )

    assert "当前目标" in artifact.content_text
    assert "继续设计 memory 系统" in artifact.content_text
    assert artifact.payload_json["kind"] == "continuation_artifact"
    assert artifact.payload_json["exclude_from_recall"] is True

