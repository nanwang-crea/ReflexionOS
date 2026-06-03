from app.memory.message_normalizer import normalize_message_text, normalize_message_text_for_seed
from app.models.conversation import Message, MessageType, StreamState


def build_message(**overrides):
    message_type = overrides.get("message_type", MessageType.ASSISTANT_MESSAGE)
    role = overrides.get("role", ("tool" if message_type == MessageType.TOOL_TRACE else "assistant"))
    payload = {
        "id": "msg-1",
        "session_id": "session-1",
        "turn_id": "turn-1",
        "run_id": "run-1",
        "turn_message_index": 1,
        "role": role,
        "message_type": message_type,
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
    assert "truncated" in normalized
    assert "DROP_ME_SEARCH_INDEX_MIDDLE" not in normalized


def test_normalize_message_text_handles_non_dict_payload_shape():
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={},
    ).model_copy(update={"payload_json": ["unexpected", "shape"]})

    normalized = normalize_message_text(message)
    assert normalized == "tool_name="


def test_normalize_message_text_for_seed_expands_tool_trace_payload():
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={
            "tool_name": "shell",
            "arguments": {"cmd": "ls"},
            "success": True,
            "output": "file1.py\nfile2.py",
        },
    )
    result = normalize_message_text_for_seed(message)
    assert "tool_name=shell" in result
    assert "success=True" in result
    assert "file1.py" in result


def test_normalize_message_text_for_seed_uses_shorter_truncation():
    output = "A-" * 2000 + "-Z"
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={
            "tool_name": "shell",
            "arguments": {"cmd": "cat large_file.txt"},
            "success": True,
            "output": output,
        },
    )
    result = normalize_message_text_for_seed(message)
    assert len(result) < 1200
    assert "A-" in result
    assert "-Z" in result
    assert "truncated" in result


def test_normalize_message_text_for_seed_returns_content_text_for_non_tool_trace():
    message = build_message(content_text="用户消息")
    assert normalize_message_text_for_seed(message) == "用户消息"
