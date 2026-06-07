from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMToolCall, MessageRole


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

    messages = builder.build(context)


    assistant_messages = [msg for msg in messages if msg.role == "assistant" and msg.tool_calls]
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

    messages = builder.build(context)

    user_contents = [message.content for message in messages if message.role == "user"]

    task_mentions = [c for c in user_contents if "检查重复 user 消息" in (c or "")]
    assert len(task_mentions) == 1


def test_build_messages_places_current_task_after_history():
    builder = build_message_builder()
    context = LoopContext(task="继续当前任务")
    context.supplemental_context = "当前目标: 修复消息上下文"
    context.add_message("user", "上一轮需求")
    context.add_message("assistant", "上一轮结论")
    context.add_message("user", "继续当前任务")

    messages = builder.build(context)

    # 当 group_count > 1（已有多轮交互），不再重复注入 Task Anchor
    # "继续当前任务" 应只出现一次（来自原始消息，不被 anchor 重复）
    assert [message.content for message in messages if message.role == "user"].count(
        "继续当前任务"
    ) == 1


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

    messages = builder.build(context)

    system_messages = [message for message in messages if message.role == "system"]
    assert len(system_messages) >= 1
    assert "autonomous coding agent" in system_messages[0].content
    assert "Tool and shell rules" in system_messages[0].content
    assert "Execution plan" in system_messages[0].content
    assert "Plan overrides stopping" in system_messages[0].content


def test_final_summary_messages_flatten_tool_protocol_history():
    builder = build_message_builder()
    context = LoopContext(task="总结工具结果")
    tool_call = LLMToolCall(id="call_alpha", name="mock", arguments={"path": "README.md"})
    context.add_message(
        "assistant",
        content="我先读取 README",
        tool_calls=[tool_call.model_dump()],
    )
    context.add_message("tool", content="README output", tool_call_id=tool_call.id)
    context.add_message("user", "请总结")

    messages = builder.build_final_summary(context)

    tool_contents = [
        m.content for m in messages
        if m.role == MessageRole.TOOL and m.content
    ]
    assert any("README output" in c for c in tool_contents)
    # Task Anchor 应在 final summary 末尾重新注入
    assert messages[-1].role == "user"
    assert messages[-1].content == "总结工具结果"


def test_task_anchor_injected_only_on_first_round():
    """Task Anchor 仅在首轮（group_count <= 1）注入，中间轮次不重复注入。"""
    builder = build_message_builder()

    # 首轮：只有初始 user 消息，group_count=1，应注入 anchor
    context_first = LoopContext(task="安装依赖")
    context_first.add_message("user", "安装依赖")
    messages_first = builder.build(context_first)
    user_contents_first = [m.content for m in messages_first if m.role == "user"]
    assert any("安装依赖" in (c or "") for c in user_contents_first)

    # 中间轮次：已执行过工具，group_count > 1，不应注入 anchor
    context_mid = LoopContext(task="安装依赖")
    tool_call = LLMToolCall(id="call_1", name="shell", arguments={"command": "pip3 list"})
    context_mid.add_message("user", "安装依赖")
    context_mid.add_message(
        "assistant",
        content="检查已安装的包",
        tool_calls=[tool_call.model_dump()],
    )
    context_mid.add_message("tool", content="mlx 0.31.1", tool_call_id=tool_call.id)
    messages_mid = builder.build(context_mid)
    user_contents_mid = [m.content for m in messages_mid if m.role == "user"]
    assert user_contents_mid.count("安装依赖") == 1


def test_task_anchor_injected_periodically():
    builder = LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=10, task_anchor_interval=5)
    context = LoopContext(task="修复 bug")
    for i in range(5):
        tc = LLMToolCall(id=f"call_{i}", name="file", arguments={"action": "read", "path": f"f{i}.py"})
        context.add_message("assistant", content=f"step {i}", tool_calls=[tc.model_dump()])
        context.add_message("tool", content=f"output {i}", tool_call_id=tc.id)

    messages = builder.build(context)
    user_contents = [m.content for m in messages if m.role == "user"]
    assert any("修复 bug" in (c or "") for c in user_contents)


def test_compaction_continue_message_injected_after_tier3():
    builder = LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=10)
    context = LoopContext(task="实现新功能")
    context.compacted_summary = "User's original intent: implement new feature"
    context.add_message("user", "实现新功能")
    tc = LLMToolCall(id="call_1", name="file", arguments={"action": "read", "path": "a.py"})
    context.add_message("assistant", content="step 1", tool_calls=[tc.model_dump()])
    context.add_message("tool", content="output 1", tool_call_id=tc.id)

    messages = builder.build(context)
    user_contents = [m.content for m in messages if m.role == "user"]
    assert any("Continue" in (c or "") for c in user_contents)



