from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMToolCall, LLMToolDefinition


def build_message_builder() -> LoopMessageBuilder:
    return LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=10)


def test_build_messages_keeps_tool_outputs_with_matching_assistant_call():
    builder = build_message_builder()
    context = LoopContext(task="检查工具消息配对")
    first_call = LLMToolCall(id="call_alpha", name="mock", arguments={"path": "a.txt"})
    second_call = LLMToolCall(id="call_beta", name="mock", arguments={"path": "b.txt"})

    context.add_message(
        "assistant",
        content="先读取两个文件",
        tool_calls=[first_call.model_dump(), second_call.model_dump()],
    )
    context.add_message("tool", content="a output", tool_call_id=first_call.id)
    context.add_message("tool", content="b output", tool_call_id=second_call.id)

    for index in range(9):
        context.add_message("user", content=f"filler {index}")

    messages = builder.build(context, tools=[])

    assistant_messages = [
        msg for msg in messages
        if msg.role == "assistant" and msg.tool_calls
    ]
    tool_messages = [msg for msg in messages if msg.role == "tool"]

    assert len(assistant_messages) == 1
    assert [tool_message.tool_call_id for tool_message in tool_messages] == [
        first_call.id,
        second_call.id,
    ]


def test_build_messages_does_not_duplicate_initial_user_task():
    builder = build_message_builder()
    context = LoopContext(task="检查重复 user 消息")
    context.add_message("user", "检查重复 user 消息")

    messages = builder.build(context, tools=[])
    user_contents = [message.content for message in messages if message.role == "user"]

    assert user_contents.count("检查重复 user 消息") == 1


def test_initial_plan_messages_include_only_text_conversation_context():
    builder = build_message_builder()
    context = LoopContext(task="继续处理")
    tool_call = LLMToolCall(id="call_alpha", name="mock", arguments={})
    context.system_sections = ["AGENTS instructions"]
    context.supplemental_context = "当前目标: 修 memory"
    context.add_message("user", "上一轮需求")
    context.add_message("assistant", "上一轮结论", tool_calls=[tool_call.model_dump()])
    context.add_message("tool", "tool output", tool_call_id=tool_call.id)
    context.add_message("user", "继续处理")

    messages = builder.build_initial_plan(context)

    contents = [message.content for message in messages if message.content]
    assert "AGENTS instructions" in contents
    assert "当前目标: 修 memory" in contents
    assert "上一轮需求" in contents
    assert "上一轮结论" in contents
    assert "tool output" not in contents
    assert all(not message.tool_calls for message in messages)


def test_system_prompt_uses_runtime_tool_definitions():
    builder = build_message_builder()
    context = LoopContext(task="检查工具列表")
    context.add_message("user", "检查工具列表")
    tools = [
        LLMToolDefinition(
            name="mock",
            description="Mock tool",
            parameters={"type": "object", "properties": {}},
        )
    ]

    messages = builder.build(context, tools=tools)

    assert messages[0].role == "system"
    assert "mock" in messages[0].content
    assert "Mock tool" in messages[0].content
