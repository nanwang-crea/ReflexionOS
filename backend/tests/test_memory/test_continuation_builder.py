from app.memory.continuation_builder import ContinuationArtifactBuilder
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


def test_continuation_builder_compresses_tool_output_with_head_and_tail():
    output = (
        "BEGIN-"
        + ("head-block-" * 20)
        + ("omitted-middle-" * 500)
        + ("tail-block-" * 20)
        + "-TAIL-END"
    )
    builder = ContinuationArtifactBuilder(
        max_transcript_chars=1_200,
        max_item_chars=600,
        max_tool_output_chars=260,
        tool_output_head_chars=90,
        tool_output_tail_chars=70,
    )

    prompt_input = builder.build_prompt_input(
        task="请继续修复 continuation artifact",
        messages=[
            build_message(
                id="msg-user",
                role="user",
                message_type=MessageType.USER_MESSAGE,
                content_text="用户要求修复 continuation artifact",
            ),
            build_message(
                id="msg-tool",
                role="assistant",
                message_type=MessageType.TOOL_TRACE,
                payload_json={
                    "tool_name": "shell",
                    "arguments": {"command": "pytest -q"},
                    "success": False,
                    "output": output,
                },
            ),
            build_message(
                id="msg-assistant",
                content_text="已经定位到 tool output 过长。",
            ),
        ],
    )

    assert len(prompt_input.transcript) <= 1_200
    assert "tool_name=shell" in prompt_input.transcript
    assert "BEGIN-" in prompt_input.transcript
    assert "-TAIL-END" in prompt_input.transcript
    assert "省略" in prompt_input.transcript
    assert "omitted-middle-omitted-middle-omitted-middle" not in prompt_input.transcript


def test_continuation_builder_excludes_existing_continuation_artifacts():
    builder = ContinuationArtifactBuilder()

    prompt_input = builder.build_prompt_input(
        task="继续",
        messages=[
            build_message(
                id="msg-old-continuation",
                role="system",
                message_type=MessageType.SYSTEM_NOTICE,
                content_text="旧的 continuation summary",
                payload_json={"kind": "continuation_artifact"},
            ),
            build_message(
                id="msg-user",
                role="user",
                message_type=MessageType.USER_MESSAGE,
                content_text="新的用户目标",
            ),
        ],
    )

    assert "旧的 continuation summary" not in prompt_input.transcript
    assert "新的用户目标" in prompt_input.transcript


def test_continuation_builder_applies_global_budget_recent_first():
    builder = ContinuationArtifactBuilder(
        max_transcript_chars=500,
        max_item_chars=180,
        max_tool_output_chars=100,
    )
    messages = [
        build_message(
            id=f"msg-old-{index}",
            turn_message_index=index,
            content_text=f"旧消息 {index} " + ("x" * 300),
        )
        for index in range(1, 8)
    ]
    messages.append(
        build_message(
            id="msg-latest-user",
            role="user",
            message_type=MessageType.USER_MESSAGE,
            turn_message_index=8,
            content_text="最新用户需求必须保留",
        )
    )

    prompt_input = builder.build_prompt_input(task="继续", messages=messages)

    assert len(prompt_input.transcript) <= 500
    assert "最新用户需求必须保留" in prompt_input.transcript
    assert "已按 continuation 预算省略" in prompt_input.transcript
