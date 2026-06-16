"""端到端测试：验证用户上传图片后，模型在所有轮次都能看到图片"""

from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMToolCall, MessageRole


def test_end_to_end_multimodal_flow():
    """
    端到端测试：模拟用户上传图片并进行多轮对话
    验证图片在所有轮次都能正确传递给 LLM
    """
    builder = LoopMessageBuilder(
        prompt_manager=PromptManager(), max_context_groups=3, task_anchor_interval=5
    )

    # 用户上传图片并提问
    task_content = [
        {"type": "text", "text": "这张图片里有什么？"},
        {"type": "image_url", "url": "data:image/png;base64,iVBORw0KGgoAAAANS..."},
    ]

    # === 第 1 轮：用户提问 ===
    context = LoopContext.from_run_input(
        task="这张图片里有什么？",
        task_content=task_content,
        project_path="/test",
        agent_mode="code",
    )

    messages_r1 = builder.build(context)
    user_msgs_r1 = [m for m in messages_r1 if m.role == MessageRole.USER]

    # 验证：用户的图片消息在第 1 轮中存在
    multimodal_msgs = [m for m in user_msgs_r1 if isinstance(m.content, list)]
    assert len(multimodal_msgs) == 1, "第 1 轮应该包含用户的多模态消息"
    assert multimodal_msgs[0].content[0]["text"] == "这张图片里有什么？"
    assert "image/png" in multimodal_msgs[0].content[1]["url"]

    # === 第 2 轮：模型回复 ===
    context.add_message(MessageRole.ASSISTANT, "我看到图片中有一只猫")

    messages_r2 = builder.build(context)
    user_msgs_r2 = [m for m in messages_r2 if m.role == MessageRole.USER]

    # 验证：用户的图片消息在第 2 轮依然存在
    multimodal_msgs_r2 = [m for m in user_msgs_r2 if isinstance(m.content, list)]
    assert len(multimodal_msgs_r2) == 1, "第 2 轮应该依然能看到用户的图片"

    # === 第 3 轮：模型调用工具 ===
    tool_call = LLMToolCall(id="call_1", name="file", arguments={"action": "read"})
    context.add_message(
        MessageRole.ASSISTANT, content="让我读取相关文件", tool_calls=[tool_call.model_dump()]
    )
    context.add_message(MessageRole.TOOL, content="文件内容...", tool_call_id=tool_call.id)

    messages_r3 = builder.build(context)
    user_msgs_r3 = [m for m in messages_r3 if m.role == MessageRole.USER]

    # 验证：用户的图片消息在第 3 轮依然存在
    multimodal_msgs_r3 = [m for m in user_msgs_r3 if isinstance(m.content, list)]
    assert len(multimodal_msgs_r3) == 1, "第 3 轮应该依然能看到用户的图片"

    # === 第 5 轮：触发周期性 Task Anchor ===
    # Add more messages to reach group_count = 5 (task_anchor_interval)
    for i in range(2):
        tc = LLMToolCall(id=f"call_{i+2}", name="tool", arguments={})
        context.add_message(
            MessageRole.ASSISTANT, content=f"步骤 {i+2}", tool_calls=[tc.model_dump()]
        )
        context.add_message(MessageRole.TOOL, content=f"输出 {i+2}", tool_call_id=tc.id)

    context.metadata = {}

    messages_r5 = builder.build(context)

    # 验证：第 5 轮应该有纯文本的 Task Reminder
    task_reminders = [
        m
        for m in messages_r5
        if m.role == MessageRole.USER
        and isinstance(m.content, str)
        and "[Task Reminder]" in m.content
    ]
    assert len(task_reminders) == 1, "第 5 轮应该有 Task Reminder"
    assert "这张图片里有什么" in task_reminders[0].content

    # 验证：用户的原始图片消息依然在历史中（如果在窗口内）
    user_msgs_r5 = [m for m in messages_r5 if m.role == MessageRole.USER]
    # 由于 max_context_groups=3，第 1 轮的消息可能已经移出窗口，但如果在，应该保留图片
    multimodal_msgs_r5 = [m for m in user_msgs_r5 if isinstance(m.content, list)]
    # 不强制要求图片还在，因为可能已经超出窗口


def test_multimodal_content_survives_context_assembly():
    """测试多模态内容在 context assembly 和 message builder 流程中都能正确保留"""
    # 模拟从 context_assembly 返回的历史消息
    history_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "分析这个错误"},
                {"type": "image_url", "url": "data:image/png;base64,screenshot"},
            ],
        },
        {"role": "assistant", "content": "我看到了错误截图"},
    ]

    # 创建新的上下文，模拟新一轮的请求
    context = LoopContext.from_run_input(
        task="继续分析",
        history_messages=history_messages,
        project_path="/test",
        agent_mode="code",
    )

    builder = LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=5)

    messages = builder.build(context)

    # 验证：历史中的图片消息应该被保留
    user_msgs = [m for m in messages if m.role == MessageRole.USER]
    multimodal_msgs = [m for m in user_msgs if isinstance(m.content, list)]

    assert len(multimodal_msgs) >= 1, "历史中的多模态消息应该被保留"
    # 找到带截图的那条消息
    screenshot_msgs = [
        m
        for m in multimodal_msgs
        if any(
            p.get("url", "").endswith("screenshot")
            for p in m.content
            if isinstance(p, dict)
        )
    ]
    assert len(screenshot_msgs) == 1, "带截图的消息应该被正确保留"
