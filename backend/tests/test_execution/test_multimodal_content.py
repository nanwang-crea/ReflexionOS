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

    messages = builder.build_initial_plan(context)

    last_msg = messages[-1]
    assert last_msg.role == "user"
    assert last_msg.content == "分析代码"
    assert isinstance(last_msg.content, str)


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

    messages = builder.build_initial_plan(context)

    last_msg = messages[-1]
    assert last_msg.role == "user"
    assert isinstance(last_msg.content, list)
    assert len(last_msg.content) == 2

    assert last_msg.content[0] == {"type": "text", "text": "请分析这张图片"}
    assert last_msg.content[1]["type"] == "image_url"
    assert "data:image/png;base64" in last_msg.content[1]["url"]


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
    """测试无效项被过滤"""
    multimodal_content = [
        {"type": "text", "text": "Valid"},
        "invalid_item",
        None,
        {"type": "image_url", "url": "data:..."},
    ]

    context = LoopContext(
        task="test",
        task_content=multimodal_content,
    )

    builder = LoopMessageBuilder(
        prompt_manager=PromptManager(model_name="gpt-4"),
        max_context_groups=10,
    )

    messages = builder.build_initial_plan(context)
    last_msg = messages[-1]
    assert isinstance(last_msg.content, list)
    assert len(last_msg.content) == 2
    assert last_msg.content[0]["text"] == "Valid"
    assert last_msg.content[1]["type"] == "image_url"
