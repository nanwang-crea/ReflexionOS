from app.config.settings import ExecutionSettings
from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.llm.base import MessageRole


def _make_builder() -> LoopMessageBuilder:
    pm = PromptManager()
    return LoopMessageBuilder(prompt_manager=pm, max_context_groups=10)


def test_execution_settings_compaction_buffer():
    settings = ExecutionSettings()
    assert settings.compaction_buffer == 20_000


def test_execution_settings_tier2_ratio():
    settings = ExecutionSettings()
    assert settings.tier2_ratio == 0.5


def test_execution_settings_tier3_ratio():
    settings = ExecutionSettings()
    assert settings.tier3_ratio == 0.85


def test_execution_settings_tool_output_max_chars():
    settings = ExecutionSettings()
    assert settings.tool_output_max_chars == 2_400


def test_execution_settings_prune_defaults():
    settings = ExecutionSettings()
    assert settings.prune_protect_groups == 2
    assert settings.prune_minimum_recovery_tokens == 20_000


def test_loop_context_tracks_total_tokens():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "Hello world")
    assert ctx.compressor.get_total_tokens() > 0


def test_loop_context_total_tokens_accumulates():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "First message")
    tokens_after_first = ctx.compressor.get_total_tokens()
    ctx.add_message("assistant", "Second message")
    assert ctx.compressor.get_total_tokens() > tokens_after_first


def test_loop_context_compacted_summary_default_none():
    ctx = LoopContext(task="hello")
    assert ctx.compressor.get_compacted_summary() is None


def test_loop_context_group_count():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "First message")
    ctx.add_message("assistant", "Response")
    assert ctx.compressor.get_group_count() >= 2


def test_loop_context_group_count_with_tool_group():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "Read file")
    ctx.add_message(
        "assistant",
        "Will read",
        tool_calls=[{"id": "c1", "name": "read_file", "arguments": {}}],
    )
    ctx.add_message("tool", "file contents", tool_call_id="c1")
    assert ctx.compressor.get_group_count() >= 2


def test_prune_tool_outputs_clears_old_tool_content():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "Read files")
    for i in range(15):
        ctx.add_message(
            "assistant",
            f"Reading {i}",
            tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}],
        )
        ctx.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")
    tokens_before = ctx.compressor.get_total_tokens()
    recovered = ctx.compressor.prune_tool_outputs(
        protect_recent_groups=2, minimum_recovery_tokens=1
    )
    assert recovered > 0
    assert ctx.compressor.get_total_tokens() < tokens_before
    tool_msgs = [
        m for m in ctx.compressor.get_messages() if m["role"] == MessageRole.TOOL
    ]
    cleared = [
        m for m in tool_msgs if m.get("content") == "[Old tool result content cleared]"
    ]
    assert len(cleared) > 0


def test_prune_tool_outputs_respects_minimum_recovery():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "Small task")
    ctx.add_message("assistant", "Done")
    ctx.add_message("tool", "small output", tool_call_id="c1")
    recovered = ctx.compressor.prune_tool_outputs(
        protect_recent_groups=2, minimum_recovery_tokens=20_000
    )
    assert recovered == 0


def test_prune_tool_outputs_protects_recent_groups():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "Read files")
    for i in range(5):
        ctx.add_message(
            "assistant",
            f"Reading {i}",
            tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}],
        )
        ctx.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")
    ctx.compressor.prune_tool_outputs(
        protect_recent_groups=3, minimum_recovery_tokens=1
    )
    grouped = ctx.compressor.get_groups()
    recent_tool_msgs = []
    for group in grouped[-3:]:
        for msg in group.messages:
            if msg["role"] == MessageRole.TOOL:
                recent_tool_msgs.append(msg)
    for msg in recent_tool_msgs:
        assert msg.get("content") != "[Old tool result content cleared]"


def test_midrun_compress_system_prompt():
    pm = PromptManager()
    prompt = pm.get_midrun_compression_system_prompt()
    assert "User's original intent" in prompt
    assert "Operations performed" in prompt
    assert "session_recall can retrieve" in prompt
    assert "Active plan constraints" in prompt
    assert "Decisions already made" in prompt


def test_glm_midrun_compress_system_prompt_preserves_plan_anchor():
    pm = PromptManager(model_name="glm-4-plus")
    prompt = pm.get_midrun_compression_system_prompt()

    assert "活动计划约束" in prompt
    assert "已做决定" in prompt


def test_midrun_compress_input_prompt():
    pm = PromptManager()
    prompt = pm.get_midrun_compression_prompt(
        task="Fix bug", transcript="some transcript"
    )
    assert "Fix bug" in prompt
    assert "some transcript" in prompt


def test_midrun_compress_input_with_existing_summary():
    pm = PromptManager()
    prompt = pm.get_midrun_compression_prompt(
        task="Fix bug",
        transcript="new messages",
        existing_summary="previous summary",
    )
    assert "previous summary" in prompt
    assert "new messages" in prompt


def test_task_anchor_injected():
    builder = _make_builder()
    ctx = LoopContext(task="Fix the login bug")
    ctx.add_message("user", "Fix the login bug")
    ctx.add_message("assistant", "I will investigate")
    messages = builder.build(ctx)
    user_contents = [m.content for m in messages if m.role == MessageRole.USER]
    assert any("Fix the login bug" in c for c in user_contents if c)


def test_task_anchor_not_duplicated_in_recent():
    builder = _make_builder()
    ctx = LoopContext(task="Fix the login bug")
    ctx.add_message("user", "Fix the login bug")
    ctx.add_message("assistant", "I will investigate")
    messages = builder.build(ctx)
    task_count = sum(
        1
        for m in messages
        if m.role == MessageRole.USER and m.content == "Fix the login bug"
    )
    assert task_count == 1


def test_compacted_summary_injected():
    builder = _make_builder()
    ctx = LoopContext(task="Fix bug")
    ctx.compressor.set_compacted_summary(
        "User's original intent: Fix bug\nOperations performed: read foo.py"
    )
    ctx.add_message("user", "Fix bug")
    ctx.add_message("assistant", "Working on it")
    messages = builder.build(ctx)
    system_contents = [
        m.content for m in messages if m.role == MessageRole.SYSTEM and m.content
    ]
    assert any("Compacted historical context" in c for c in system_contents if c)


def test_tier2_messages_preserve_tool_role():
    builder = _make_builder()
    ctx = LoopContext(task="Read files")
    long_output = "A" * 5000
    for i in range(15):
        ctx.add_message(
            "assistant",
            f"Reading file {i}",
            tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}],
        )
        ctx.add_message("tool", long_output, tool_call_id=f"c{i}")
    messages = builder.build(ctx)
    tier2_tool_msgs = [
        m
        for m in messages
        if m.role == MessageRole.TOOL and m.content and "truncated" in m.content
    ]
    assert len(tier2_tool_msgs) > 0
    for m in tier2_tool_msgs:
        assert m.tool_call_id is not None


def test_tier2_messages_preserve_assistant_role_with_tool_calls():
    builder = _make_builder()
    ctx = LoopContext(task="Read files")
    for i in range(15):
        ctx.add_message(
            "assistant",
            f"Reading file {i}",
            tool_calls=[
                {
                    "id": f"c{i}",
                    "name": "read_file",
                    "arguments": {"path": f"src/{i}.py"},
                }
            ],
        )
        ctx.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")
    messages = builder.build(ctx)
    tier2_assistant_msgs = [
        m for m in messages if m.role == MessageRole.ASSISTANT and m.tool_calls
    ]
    assert len(tier2_assistant_msgs) > 0


def test_tier2_handles_pruned_tool_outputs():
    builder = _make_builder()
    ctx = LoopContext(task="Read files")
    for i in range(15):
        ctx.add_message(
            "assistant",
            f"Reading file {i}",
            tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}],
        )
        ctx.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")
    ctx.compressor.prune_tool_outputs(
        protect_recent_groups=2, minimum_recovery_tokens=1
    )
    messages = builder.build(ctx)
    cleared_msgs = [
        m
        for m in messages
        if m.role == MessageRole.TOOL
        and m.content == "[Old tool result content cleared]"
    ]
    assert len(cleared_msgs) > 0


def test_full_three_tier_flow():
    builder = _make_builder()
    task = "Refactor the authentication module to support OAuth2"
    ctx = LoopContext(task=task)
    ctx.add_message("user", task)
    for i in range(25):
        ctx.add_message(
            "assistant",
            f"Reading file {i}",
            tool_calls=[
                {
                    "id": f"c{i}",
                    "name": "read_file",
                    "arguments": {"path": f"src/{i}.py"},
                }
            ],
        )
        ctx.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")

    messages = builder.build(ctx)

    has_task_anchor = any(
        m.role == MessageRole.USER and m.content == task for m in messages
    )
    assert has_task_anchor

    has_tier2_truncated = any(
        m.role == MessageRole.TOOL and m.content and "truncated" in m.content
        for m in messages
    )
    assert has_tier2_truncated

    user_task_count = sum(
        1 for m in messages if m.role == MessageRole.USER and m.content == task
    )
    assert user_task_count == 1


def test_task_anchor_preserves_original_intent():
    builder = _make_builder()
    task = (
        "Please fix the bug where users can't login with SSO. "
        "The error is in auth.py line 42."
    )
    ctx = LoopContext(task=task)
    for i in range(15):
        ctx.add_message(
            "assistant",
            f"Step {i}",
            tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}],
        )
        ctx.add_message("tool", "B" * 3000, tool_call_id=f"c{i}")

    # 中间执行轮次：group_count > 1，不注入 Task Anchor
    messages = builder.build(ctx)
    anchor = next(
        (
            m
            for m in messages
            if m.role == MessageRole.USER and "SSO" in (m.content or "")
        ),
        None,
    )
    assert anchor is None

    # 但在 final summary 中，Task Anchor 重新注入，确保回答围绕原始任务
    summary_messages = builder.build_final_summary(ctx)
    summary_anchor = next(
        (
            m
            for m in summary_messages
            if m.role == MessageRole.USER and "SSO" in (m.content or "")
        ),
        None,
    )
    assert summary_anchor is not None
    assert "auth.py line 42" in summary_anchor.content
