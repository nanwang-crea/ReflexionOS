"""测试多模态内容（文本+图片）的处理"""

from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager


def test_task_content_with_text_only():
    """测试纯文本 task_content"""
    context = LoopContext(task="分析代码", task_content="分析代码")
    builder = LoopMessageBuilder(
        prompt_manager=PromptManager(model_name="gpt-4"),
        max_context_groups=10,
    )

    context.add_message("user", "分析代码")
    messages = builder.build(context)

    user_msgs = [m for m in messages if m.role == "user"]
    assert len(user_msgs) >= 1
    assert any("分析代码" in (c or "") for c in [m.content for m in user_msgs])


def test_task_content_with_multimodal():
    """测试多模态 task_content（文本+图片）"""
    multimodal_content = [
        {"type": "text", "text": "请分析这张图片"},
        {"type": "image_url", "url": "data:image/png;base64,iVBORw0KGgoAAAANS..."},
    ]

    context = LoopContext(
        task="请分析这张图片",
        task_content=multimodal_content,
    )

    builder = LoopMessageBuilder(
        prompt_manager=PromptManager(model_name="gpt-4"),
        max_context_groups=10,
    )

    context.add_message("user", multimodal_content)
    messages = builder.build(context)

    # 找到包含多模态内容的 user 消息
    user_msgs = [m for m in messages if m.role == "user"]
    multimodal_msgs = [m for m in user_msgs if isinstance(m.content, list)]
    assert len(multimodal_msgs) >= 1
    msg = multimodal_msgs[0]
    assert len(msg.content) == 2
    assert msg.content[0] == {"type": "text", "text": "请分析这张图片"}
    assert msg.content[1]["type"] == "image_url"
    assert "data:image/png;base64" in msg.content[1]["url"]


def test_task_content_multimodal_in_final_summary():
    """测试 final_summary 中的多模态内容"""
    multimodal_content = [
        {"type": "text", "text": "总结一下"},
        {"type": "image_url", "url": "data:image/jpeg;base64,/9j/4AAQSkZJ..."},
    ]

    context = LoopContext(
        task="总结一下",
        task_content=multimodal_content,
    )

    builder = LoopMessageBuilder(
        prompt_manager=PromptManager(model_name="gpt-4"),
        max_context_groups=10,
    )

    messages = builder.build_final_summary(context)

    last_msg = messages[-1]
    assert last_msg.role == "user"
    assert isinstance(last_msg.content, list)
    assert len(last_msg.content) == 2

    assert last_msg.content[0]["type"] == "text"
    assert last_msg.content[1]["type"] == "image_url"


def test_task_content_filters_invalid_items():
    """测试 from_run_input 过滤无效项"""
    multimodal_content = [
        {"type": "text", "text": "Valid"},
        "invalid_item",
        None,
        {"type": "image_url", "url": "data:..."},
    ]

    context = LoopContext.from_run_input(
        task="test",
        task_content=multimodal_content,
    )

    # from_run_input 会跳过非 dict 的无效项，只保留有效的 dict 项
    # task_content 被过滤后只包含 2 个有效项
    assert isinstance(context.task_content, list)
    assert len(context.task_content) == 2
    assert context.task_content[0] == {"type": "text", "text": "Valid"}
    assert context.task_content[1]["type"] == "image_url"
