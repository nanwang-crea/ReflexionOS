"""测试 Task Anchor 注入和用户消息多模态内容的完整流程"""
import pytest
from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.llm.base import MessageRole


class TestMultimodalMessageFlow:
    """测试多模态消息在整个流程中的传递"""

    @pytest.fixture
    def prompt_manager(self):
        return PromptManager()

    @pytest.fixture
    def builder(self, prompt_manager):
        return LoopMessageBuilder(
            prompt_manager=prompt_manager,
            max_context_groups=3,
            task_anchor_interval=5
        )

    def test_first_turn_user_message_with_images(self, builder):
        """首轮：用户消息（带图片）应该在 context.messages 中，不需要 Task Anchor"""
        context = LoopContext(
            task="分析这张图片",
            task_content=[
                {"type": "text", "text": "分析这张图片"},
                {"type": "image_url", "url": "data:image/png;base64,abc123"}
            ],
            project_path="/test",
            agent_mode="code",
            session_id="test_session"
        )

        # 模拟用户消息已添加到 context.messages
        context.add_message("user", context.task_content)

        messages = builder.build(context)

        # 找到用户消息（带图片）
        user_msgs = [m for m in messages if m.role == MessageRole.USER and isinstance(m.content, list)]
        assert len(user_msgs) == 1, "应该有一条用户消息包含多模态内容"

        content = user_msgs[0].content
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "分析这张图片"
        assert content[1]["type"] == "image_url"
        assert "base64" in content[1]["url"]

        # 首轮不应该有 Task Reminder
        task_reminders = [m for m in messages if m.role == MessageRole.USER and "[Task Reminder]" in str(m.content)]
        assert len(task_reminders) == 0, "首轮不需要 Task Reminder"

    def test_subsequent_turns_preserve_user_images(self, builder):
        """后续轮次：用户的图片消息应该保留在历史中"""
        context = LoopContext(
            task="分析这张图片",
            task_content=[
                {"type": "text", "text": "分析这张图片"},
                {"type": "image_url", "url": "data:image/png;base64,abc123"}
            ],
            project_path="/test",
            agent_mode="code",
            session_id="test_session"
        )

        # 模拟多轮对话
        context.add_message("user", context.task_content)
        context.add_message("assistant", "这是一张...")

        messages = builder.build(context)

        # 用户的图片消息应该依然在历史中
        user_msgs = [m for m in messages if m.role == MessageRole.USER and isinstance(m.content, list)]
        assert len(user_msgs) == 1, "用户的多模态消息应该保留在历史中"

    def test_periodic_task_reminder_is_text_only(self, builder):
        """周期性 Task Reminder 只需要纯文本提醒即可"""
        context = LoopContext(
            task="检查代码",
            task_content=[
                {"type": "text", "text": "检查代码"},
                {"type": "image_url", "url": "data:image/png;base64,xyz789"}
            ],
            project_path="/test",
            agent_mode="code",
            session_id="test_session"
        )

        context.add_message("user", context.task_content)
        # 模拟对话到第 5 轮（但不超过 max_context_groups=3 的窗口）
        context.add_message("assistant", "第 1 次回复", tool_calls=[{"id": "tc1", "name": "tool1", "arguments": {}}])
        context.add_message("tool", "工具输出", tool_call_id="tc1")
        # Add more messages to reach group_count = 5
        context.add_message("assistant", "第 2 次回复", tool_calls=[{"id": "tc2", "name": "tool2", "arguments": {}}])
        context.add_message("tool", "工具输出2", tool_call_id="tc2")
        context.add_message("assistant", "第 3 次回复", tool_calls=[{"id": "tc3", "name": "tool3", "arguments": {}}])
        context.add_message("tool", "工具输出3", tool_call_id="tc3")
        context.add_message("assistant", "第 4 次回复", tool_calls=[{"id": "tc4", "name": "tool4", "arguments": {}}])
        context.add_message("tool", "工具输出4", tool_call_id="tc4")
        context.metadata = {}

        messages = builder.build(context)

        # 应该有一条纯文本的 Task Reminder
        task_reminders = [m for m in messages if m.role == MessageRole.USER and "[Task Reminder]" in str(m.content)]
        assert len(task_reminders) == 1, "周期注入应该有 Task Reminder"
        assert isinstance(task_reminders[0].content, str), "Task Reminder 应该是纯文本"
        assert task_reminders[0].content == "[Task Reminder] 检查代码"

        # 原始的用户图片消息也应该在历史中（因为在 max_context_groups 窗口内）
        user_msgs = [m for m in messages if m.role == MessageRole.USER and isinstance(m.content, list)]
        assert len(user_msgs) == 1, "原始用户消息（带图片）应该也在历史中"

    def test_no_anchor_between_intervals(self, builder):
        """非周期点时不应该注入 Task Anchor"""
        context = LoopContext(
            task="任务描述",
            task_content=[
                {"type": "text", "text": "任务描述"},
                {"type": "image_url", "url": "data:image/png;base64,test"}
            ],
            project_path="/test",
            agent_mode="code",
            session_id="test_session"
        )
        context.add_message("user", context.task_content)

        messages = builder.build(context)

        # 不应该有 Task Reminder
        task_reminders = [m for m in messages if m.role == MessageRole.USER and "[Task Reminder]" in str(m.content)]
        assert len(task_reminders) == 0, "非周期点不应该注入 Task Anchor"

        # 但用户的多模态消息应该在历史中
        user_msgs = [m for m in messages if m.role == MessageRole.USER and isinstance(m.content, list)]
        assert len(user_msgs) == 1

    def test_context_from_run_input_with_multimodal(self):
        """测试 LoopContext.from_run_input 正确处理多模态 task_content"""
        task_content = [
            {"type": "text", "text": "分析图片"},
            {"type": "image_url", "url": "data:image/png;base64,test123"}
        ]

        context = LoopContext.from_run_input(
            task="分析图片",
            task_content=task_content,
            project_path="/test",
            agent_mode="code",
        )

        # 用户消息应该包含多模态内容
        user_msgs = [m for m in context.messages if m["role"] == MessageRole.USER]
        assert len(user_msgs) == 1
        assert isinstance(user_msgs[0]["content"], list)
        assert len(user_msgs[0]["content"]) == 2
        assert user_msgs[0]["content"][0]["type"] == "text"
        assert user_msgs[0]["content"][1]["type"] == "image_url"

    def test_history_messages_with_multimodal_preserved(self):
        """测试从历史消息恢复时保留多模态内容"""
        history_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看这张图"},
                    {"type": "image_url", "url": "data:image/png;base64,old"}
                ]
            },
            {"role": "assistant", "content": "好的，我看到了"}
        ]

        context = LoopContext.from_run_input(
            task="继续分析",
            history_messages=history_messages,
            project_path="/test",
            agent_mode="code",
        )

        # 历史中的多模态消息应该被保留
        user_msgs = [m for m in context.messages if m["role"] == MessageRole.USER]
        multimodal_msgs = [m for m in user_msgs if isinstance(m["content"], list)]
        assert len(multimodal_msgs) >= 1, "历史中的多模态消息应该被保留"
