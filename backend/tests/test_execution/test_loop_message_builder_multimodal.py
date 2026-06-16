from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.llm.base import MessageRole


def test_loop_message_builder_skips_task_anchor_for_multimodal_current_turn():
    context = LoopContext.from_run_input(
        task="你好，看一下图片内容，为什么报错呢",
        current_turn_message={
            "role": "user",
            "content": [
                {"type": "text", "text": "你好，看一下图片内容，为什么报错呢"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
            ],
        },
    )

    builder = LoopMessageBuilder(
        prompt_manager=PromptManager(),
        max_context_groups=8,
        tool_output_max_chars=2400,
    )
    messages = builder.build(context)

    user_messages = [message for message in messages if message.role == MessageRole.USER]
    assert len(user_messages) == 1
    assert isinstance(user_messages[0].content, list)
