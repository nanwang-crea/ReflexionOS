"""上下文压缩器单元测试"""

import pytest
from app.execution.context_compressor import ContextCompressor, MessageGroup


def test_add_message_updates_tokens():
    """测试添加消息后 token 自动更新"""
    compressor = ContextCompressor()

    compressor.add_message("user", "Hello world")

    assert compressor.get_message_count() == 1
    assert compressor.get_total_tokens() > 0


def test_add_message_with_tool_calls():
    """测试添加带工具调用的消息"""
    compressor = ContextCompressor()

    compressor.add_message(
        "assistant",
        "Let me read the file",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {"path": "test.py"}}],
    )

    assert compressor.get_message_count() == 1
    assert compressor.get_total_tokens() > 0
    messages = compressor.get_messages()
    assert messages[0]["tool_calls"][0]["name"] == "read"


def test_add_message_with_multimodal_content():
    """测试添加多模态消息"""
    compressor = ContextCompressor()

    multimodal_content = [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image", "source": {"type": "base64", "data": "fake_base64"}},
    ]

    compressor.add_message("user", multimodal_content)

    assert compressor.get_message_count() == 1
    messages = compressor.get_messages()
    assert isinstance(messages[0]["content"], list)
    assert len(messages[0]["content"]) == 2


def test_group_messages_with_tool_calls():
    """测试 assistant+tool_calls 分组逻辑"""
    messages = [
        {"role": "user", "content": "test"},
        {
            "role": "assistant",
            "content": "ok",
            "tool_calls": [{"id": "c1", "name": "read", "arguments": {}}],
        },
        {"role": "tool", "content": "output", "tool_call_id": "c1"},
    ]

    groups = ContextCompressor.group_messages(messages)

    assert len(groups) == 2
    assert groups[0].messages[0]["role"] == "user"
    assert groups[1].messages[0]["role"] == "assistant"
    assert len(groups[1].messages) == 2  # assistant + tool


def test_group_messages_multiple_tools():
    """测试一个 assistant 调用多个工具的分组"""
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "c1", "name": "read", "arguments": {}},
                {"id": "c2", "name": "bash", "arguments": {}},
            ],
        },
        {"role": "tool", "content": "file content", "tool_call_id": "c1"},
        {"role": "tool", "content": "bash output", "tool_call_id": "c2"},
    ]

    groups = ContextCompressor.group_messages(messages)

    assert len(groups) == 1
    assert len(groups[0].messages) == 3  # assistant + 2 tools


def test_group_messages_standalone_user():
    """测试单独的 user 消息成组"""
    messages = [
        {"role": "user", "content": "message 1"},
        {"role": "user", "content": "message 2"},
    ]

    groups = ContextCompressor.group_messages(messages)

    assert len(groups) == 2
    assert len(groups[0].messages) == 1
    assert len(groups[1].messages) == 1


def test_get_recent_messages_returns_last_n_groups():
    """测试 Tier 1 获取最近 N 组"""
    compressor = ContextCompressor(max_context_groups=2)

    for i in range(5):
        compressor.add_message("user", f"msg {i}")

    recent = compressor.get_recent_messages()

    assert len(recent) == 2
    assert recent[0]["content"] == "msg 3"
    assert recent[1]["content"] == "msg 4"


def test_get_recent_messages_with_tool_groups():
    """测试 Tier 1 获取最近 N 组（包含工具调用组）"""
    compressor = ContextCompressor(max_context_groups=2)

    # 添加 3 组消息
    compressor.add_message("user", "msg 0")
    compressor.add_message(
        "assistant", "", tool_calls=[{"id": "c1", "name": "read", "arguments": {}}]
    )
    compressor.add_message("tool", "output 1", tool_call_id="c1")
    compressor.add_message("user", "msg 2")

    recent = compressor.get_recent_messages()

    # 应该保留最近 2 组：assistant+tool 和最后的 user
    assert len(recent) == 3
    assert recent[0]["role"] == "assistant"
    assert recent[1]["role"] == "tool"
    assert recent[2]["role"] == "user"


def test_check_pressure_returns_true_when_over_threshold():
    """测试压力检测阈值"""
    compressor = ContextCompressor()

    # 添加大量消息，确保超过阈值
    for i in range(100):
        compressor.add_message("user", "A" * 2000)

    assert compressor.check_pressure(context_window=100_000, tier3_ratio=0.1)


def test_check_pressure_returns_false_when_under_threshold():
    """测试压力未超阈值"""
    compressor = ContextCompressor()

    compressor.add_message("user", "Short message")

    assert not compressor.check_pressure(context_window=100_000, tier3_ratio=0.9)


@pytest.mark.asyncio
async def test_compact_tier3_removes_old_messages():
    """测试 Tier 3 压缩移除旧消息"""
    compressor = ContextCompressor(max_context_groups=2)

    for i in range(10):
        compressor.add_message("user", f"old message {i}")

    original_count = compressor.get_message_count()

    async def mock_summarizer(task: str, transcript: str) -> str:
        return "Summary of old messages"

    await compressor.compact_tier3("test task", mock_summarizer)

    assert compressor.get_message_count() < original_count
    assert compressor.get_compacted_summary() == "Summary of old messages"


@pytest.mark.asyncio
async def test_compact_tier3_preserves_recent_groups():
    """测试 Tier 3 压缩保留最近的分组"""
    compressor = ContextCompressor(max_context_groups=3)

    for i in range(10):
        compressor.add_message("user", f"message {i}")

    async def mock_summarizer(task: str, transcript: str) -> str:
        return "Summary"

    await compressor.compact_tier3("task", mock_summarizer)

    # 应该保留最近 3 条消息
    messages = compressor.get_messages()
    assert len(messages) == 3
    assert messages[-1]["content"] == "message 9"


@pytest.mark.asyncio
async def test_compact_tier3_skips_when_under_threshold():
    """测试 Tier 3 压缩在未超阈值时跳过"""
    compressor = ContextCompressor(max_context_groups=10)

    compressor.add_message("user", "message 1")
    compressor.add_message("user", "message 2")

    async def mock_summarizer(task: str, transcript: str) -> str:
        return "Should not be called"

    await compressor.compact_tier3("task", mock_summarizer)

    # 分组数未超阈值，不应压缩
    assert compressor.get_compacted_summary() is None
    assert compressor.get_message_count() == 2


@pytest.mark.asyncio
async def test_compact_tier3_handles_empty_summary():
    """测试 Tier 3 压缩处理空摘要"""
    compressor = ContextCompressor(max_context_groups=2)

    for i in range(10):
        compressor.add_message("user", f"message {i}")

    original_count = compressor.get_message_count()

    async def mock_summarizer(task: str, transcript: str) -> str:
        return ""  # 返回空摘要

    await compressor.compact_tier3("task", mock_summarizer)

    # 空摘要时应跳过压缩
    assert compressor.get_message_count() == original_count
    assert compressor.get_compacted_summary() is None


def test_prune_tool_outputs_clears_old_content():
    """测试轻量裁剪清除旧内容"""
    compressor = ContextCompressor()

    for i in range(10):
        compressor.add_message(
            "assistant",
            f"step {i}",
            tool_calls=[{"id": f"c{i}", "name": "read", "arguments": {}}],
        )
        compressor.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")

    recovered = compressor.prune_tool_outputs(
        protect_recent_groups=2, minimum_recovery_tokens=1
    )

    assert recovered > 0
    messages = compressor.get_messages()
    cleared = [
        m for m in messages if m.get("content") == "[Old tool result content cleared]"
    ]
    assert len(cleared) > 0


def test_prune_tool_outputs_protects_recent():
    """测试轻量裁剪保护最近的分组"""
    compressor = ContextCompressor()

    for i in range(5):
        compressor.add_message(
            "assistant",
            "",
            tool_calls=[{"id": f"c{i}", "name": "read", "arguments": {}}],
        )
        compressor.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")

    compressor.prune_tool_outputs(protect_recent_groups=2, minimum_recovery_tokens=1)

    messages = compressor.get_messages()
    # 最近 2 组应该保持原样
    recent_tools = [m for m in messages[-4:] if m["role"] == "tool"]
    for tool_msg in recent_tools:
        assert tool_msg["content"] != "[Old tool result content cleared]"


def test_prune_respects_protected_tools():
    """测试轻量裁剪尊重受保护的工具"""
    compressor = ContextCompressor()

    # 添加普通工具
    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {}}],
    )
    compressor.add_message("tool", "A" * 5000, tool_call_id="c1")

    # 添加受保护的工具（skill）
    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c2", "name": "skill", "arguments": {}}],
    )
    compressor.add_message("tool", "B" * 5000, tool_call_id="c2")

    # 添加一个最近的消息以确保前面的组不被保护
    compressor.add_message("user", "recent message")

    compressor.prune_tool_outputs(
        protect_recent_groups=1,
        minimum_recovery_tokens=1,
        protected_tool_names={"skill"},
    )

    messages = compressor.get_messages()
    # read 的输出应该被清除
    assert messages[1]["content"] == "[Old tool result content cleared]"
    # skill 的输出应该保留
    assert messages[3]["content"] == "B" * 5000


def test_prune_skips_when_under_minimum():
    """测试裁剪在回收量不足时跳过"""
    compressor = ContextCompressor()

    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {}}],
    )
    compressor.add_message("tool", "short output", tool_call_id="c1")

    recovered = compressor.prune_tool_outputs(
        protect_recent_groups=0,
        minimum_recovery_tokens=100_000,  # 很高的阈值
    )

    assert recovered == 0
    messages = compressor.get_messages()
    assert messages[1]["content"] == "short output"


def test_clear_messages_resets_all_state():
    """测试清空消息重置所有状态"""
    compressor = ContextCompressor()

    compressor.add_message("user", "message 1")
    compressor.add_message("user", "message 2")

    compressor.clear_messages()

    assert compressor.get_message_count() == 0
    assert compressor.get_total_tokens() == 0
    assert compressor.get_group_count() == 0
    assert compressor.get_compacted_summary() is None


def test_build_tier2_messages_truncates_long_outputs():
    """测试 Tier 2 截断长输出"""
    compressor = ContextCompressor(max_context_groups=1, tool_output_max_chars=100)

    # 添加两组消息，第一组会进入 Tier 2
    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {}}],
    )
    compressor.add_message("tool", "A" * 500, tool_call_id="c1")

    # 添加第二组保持在 Tier 1
    compressor.add_message("user", "recent message")

    tier2_messages = compressor.build_tier2_messages()

    # 应该有 2 条消息：assistant + tool
    assert len(tier2_messages) == 2
    assert tier2_messages[0].role == "assistant"
    assert tier2_messages[1].role == "tool"
    # tool 输出应该被截断
    assert len(tier2_messages[1].content) < 500
    assert (
        "session_recall" in tier2_messages[1].content
        or "truncated" in tier2_messages[1].content
    )


def test_build_tier2_messages_preserves_tool_call_id():
    """测试 Tier 2 保留 tool_call_id"""
    compressor = ContextCompressor(max_context_groups=1)

    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "call_123", "name": "read", "arguments": {}}],
    )
    compressor.add_message("tool", "output", tool_call_id="call_123")
    compressor.add_message("user", "recent")

    tier2_messages = compressor.build_tier2_messages()

    assert tier2_messages[1].tool_call_id == "call_123"


def test_build_tier2_messages_handles_cleared_content():
    """测试 Tier 2 处理已清除的内容"""
    compressor = ContextCompressor(max_context_groups=1)

    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {}}],
    )
    compressor.add_message("tool", "A" * 5000, tool_call_id="c1")
    compressor.add_message("user", "recent")

    # 先裁剪 - 需要足够大的内容才能触发
    # 并且需要有足够的组来满足 protect_recent_groups
    compressor.add_message("user", "another message")
    compressor.prune_tool_outputs(protect_recent_groups=1, minimum_recovery_tokens=1)

    # 构建 Tier 2
    tier2_messages = compressor.build_tier2_messages()

    # 第一组的 tool 输出应该被清除
    assert tier2_messages[1].content == "[Old tool result content cleared]"


def test_build_tier2_messages_preserves_multimodal_content():
    """测试 Tier 2 保留多模态内容"""
    compressor = ContextCompressor(max_context_groups=1)

    multimodal_content = [
        {"type": "text", "text": "Check this"},
        {"type": "image", "source": {"type": "base64", "data": "fake_data"}},
    ]

    compressor.add_message("user", multimodal_content)
    compressor.add_message("user", "recent")

    tier2_messages = compressor.build_tier2_messages()

    assert len(tier2_messages) == 1
    assert tier2_messages[0].role == "user"
    assert isinstance(tier2_messages[0].content, list)
    assert len(tier2_messages[0].content) == 2


def test_build_tier2_returns_empty_when_under_threshold():
    """测试 Tier 2 在分组数不超阈值时返回空"""
    compressor = ContextCompressor(max_context_groups=10)

    compressor.add_message("user", "message 1")
    compressor.add_message("user", "message 2")

    tier2_messages = compressor.build_tier2_messages()

    assert len(tier2_messages) == 0


def test_get_groups_returns_message_groups():
    """测试获取消息分组"""
    compressor = ContextCompressor()

    compressor.add_message("user", "msg 1")
    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {}}],
    )
    compressor.add_message("tool", "output", tool_call_id="c1")

    groups = compressor.get_groups()

    assert len(groups) == 2
    assert isinstance(groups[0], MessageGroup)
    assert isinstance(groups[1], MessageGroup)
    assert groups[0].token_count > 0
    assert groups[1].token_count > 0


def test_message_group_has_tool_calls_property():
    """测试 MessageGroup 的 has_tool_calls 属性"""
    # 有工具调用的组
    group_with_tools = MessageGroup(
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "name": "read", "arguments": {}}],
            },
            {"role": "tool", "content": "output", "tool_call_id": "c1"},
        ],
        token_count=100,
    )
    assert group_with_tools.has_tool_calls is True

    # 无工具调用的组
    group_without_tools = MessageGroup(
        messages=[{"role": "user", "content": "hello"}],
        token_count=10,
    )
    assert group_without_tools.has_tool_calls is False


def test_message_group_first_message_role():
    """测试 MessageGroup 的 first_message_role 属性"""
    group = MessageGroup(
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "name": "read", "arguments": {}}],
            },
            {"role": "tool", "content": "output", "tool_call_id": "c1"},
        ],
        token_count=100,
    )
    assert group.first_message_role == "assistant"


def test_calculate_tokens():
    """测试计算消息列表的 token 数"""
    compressor = ContextCompressor()

    messages = [
        {"role": "user", "content": "Hello world"},
        {"role": "assistant", "content": "Hi there"},
    ]

    tokens = compressor.calculate_tokens(messages)
    assert tokens > 0


def test_recalculate_tokens():
    """测试重新计算总 token 数"""
    compressor = ContextCompressor()

    compressor.add_message("user", "message 1")
    compressor.add_message("user", "message 2")

    original_tokens = compressor.get_total_tokens()

    # 手动修改消息（模拟压缩后的场景）
    compressor._messages[0]["content"] = "short"

    compressor.recalculate_tokens()

    new_tokens = compressor.get_total_tokens()
    assert new_tokens != original_tokens


def test_get_group_count():
    """测试获取分组数"""
    compressor = ContextCompressor()

    compressor.add_message("user", "msg 1")
    assert compressor.get_group_count() == 1

    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {}}],
    )
    assert compressor.get_group_count() == 2

    # tool 消息归入当前组，不增加计数
    compressor.add_message("tool", "output", tool_call_id="c1")
    assert compressor.get_group_count() == 2


def test_add_message_with_timestamp():
    """测试添加消息时自动添加时间戳"""
    compressor = ContextCompressor()

    compressor.add_message("user", "test")

    messages = compressor.get_messages()
    assert "timestamp" in messages[0]
    assert messages[0]["timestamp"] is not None


def test_get_messages_returns_deep_copy():
    """测试 get_messages 返回深拷贝"""
    compressor = ContextCompressor()

    compressor.add_message("user", "original")

    messages = compressor.get_messages()
    messages[0]["content"] = "modified"

    # 原始消息不应被修改
    original_messages = compressor.get_messages()
    assert original_messages[0]["content"] == "original"


def test_edge_case_empty_compressor():
    """测试空压缩器的边界情况"""
    compressor = ContextCompressor()

    assert compressor.get_message_count() == 0
    assert compressor.get_total_tokens() == 0
    assert compressor.get_group_count() == 0
    assert compressor.get_messages() == []
    assert compressor.get_recent_messages() == []
    assert compressor.get_groups() == []
    assert compressor.build_tier2_messages() == []
    assert compressor.get_compacted_summary() is None


def test_edge_case_assistant_without_tool_calls():
    """测试 assistant 消息没有 tool_calls 的情况"""
    compressor = ContextCompressor()

    compressor.add_message("assistant", "Just a text response")

    assert compressor.get_message_count() == 1
    assert compressor.get_group_count() == 1

    groups = compressor.get_groups()
    assert len(groups) == 1
    assert groups[0].has_tool_calls is False


def test_edge_case_tool_without_active_group():
    """测试 tool 消息在没有活跃组时的分组"""
    messages = [
        {"role": "user", "content": "test"},
        {"role": "tool", "content": "orphaned tool", "tool_call_id": "c1"},
    ]

    groups = ContextCompressor.group_messages(messages)

    # tool 消息没有活跃组时应该单独成组
    assert len(groups) == 2
    assert groups[1].messages[0]["role"] == "tool"


@pytest.mark.asyncio
async def test_compact_tier3_handles_exception():
    """测试 Tier 3 压缩处理异常"""
    compressor = ContextCompressor(max_context_groups=2)

    for i in range(10):
        compressor.add_message("user", f"message {i}")

    original_count = compressor.get_message_count()

    async def failing_summarizer(task: str, transcript: str) -> str:
        raise Exception("Summarizer failed")

    # 应该静默处理异常，不影响消息
    await compressor.compact_tier3("task", failing_summarizer)

    assert compressor.get_message_count() == original_count
    assert compressor.get_compacted_summary() is None


def test_prune_already_cleared_messages():
    """测试裁剪已经被清除的消息"""
    compressor = ContextCompressor()

    compressor.add_message(
        "assistant",
        "",
        tool_calls=[{"id": "c1", "name": "read", "arguments": {}}],
    )
    compressor.add_message("tool", "A" * 5000, tool_call_id="c1")

    # 添加一个最近的消息以确保前面的组不在保护范围内
    compressor.add_message("user", "recent message")

    # 第一次裁剪
    recovered1 = compressor.prune_tool_outputs(
        protect_recent_groups=1, minimum_recovery_tokens=1
    )
    assert recovered1 > 0

    # 第二次裁剪应该跳过已清除的消息
    recovered2 = compressor.prune_tool_outputs(
        protect_recent_groups=0, minimum_recovery_tokens=1
    )
    assert recovered2 == 0
