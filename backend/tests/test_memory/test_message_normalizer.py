from app.memory.message_normalizer import normalize_message_text
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


def test_normalize_message_text_uses_content_for_assistant_messages():
    message = build_message(content_text="最终答案")
    assert normalize_message_text(message) == "最终答案"


def test_normalize_message_text_expands_tool_trace_payload():
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={
            "tool_name": "shell",
            "arguments": {"cmd": "pytest -q"},
            "success": False,
            "output": "",
            "error": "exit status 1",
        },
    )
    normalized = normalize_message_text(message)
    assert normalized == (
        "tool_name=shell\n"
        'arguments={"cmd": "pytest -q"}\n'
        "success=False\n"
        "output=\n"
        "error=exit status 1"
    )


def test_normalize_message_text_handles_tool_trace_payload_json_string():
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={},
    ).model_copy(
        update={
            "payload_json": '{"tool_name":"shell","arguments":{"cmd":"pytest -q"},"success":true}',
        }
    )

    normalized = normalize_message_text(message)
    assert normalized == ('tool_name=shell\narguments={"cmd": "pytest -q"}\nsuccess=True')


def test_normalize_message_text_compacts_large_tool_output():
    output = (
        "BEGIN-"
        + ("head-block-" * 300)
        + ("DROP_ME_SEARCH_INDEX_MIDDLE-" * 1_000)
        + ("tail-block-" * 200)
        + "-TAIL-END"
    )
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={
            "tool_name": "shell",
            "arguments": {"cmd": "pytest -q"},
            "success": True,
            "output": output,
        },
    )

    normalized = normalize_message_text(message)

    assert len(normalized) < 5_000
    assert "BEGIN-" in normalized
    assert "-TAIL-END" in normalized
    assert "省略" in normalized
    assert "DROP_ME_SEARCH_INDEX_MIDDLE" not in normalized


def test_normalize_message_text_handles_non_dict_payload_shape():
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={},
    ).model_copy(update={"payload_json": ["unexpected", "shape"]})

    normalized = normalize_message_text(message)
    assert normalized == "tool_name="
