from app.config.settings import ExecutionSettings
from app.execution.context_manager import LoopContext
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.llm.base import MessageRole
from app.llm.token_counter import count_messages_tokens


def _make_builder() -> LoopMessageBuilder:
    pm = PromptManager()
    return LoopMessageBuilder(prompt_manager=pm, max_context_groups=10)


def test_execution_settings_tier2_threshold():
    settings = ExecutionSettings()
    assert settings.tier2_truncate_threshold_tokens == 50_000


def test_execution_settings_tier3_threshold():
    settings = ExecutionSettings()
    assert settings.tier3_compact_threshold_tokens == 100_000


def test_execution_settings_tool_output_max_chars():
    settings = ExecutionSettings()
    assert settings.tool_output_max_chars == 2_400


def test_loop_context_tracks_total_tokens():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "Hello world")
    assert ctx.total_tokens > 0


def test_loop_context_total_tokens_accumulates():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "First message")
    tokens_after_first = ctx.total_tokens
    ctx.add_message("assistant", "Second message")
    assert ctx.total_tokens > tokens_after_first


def test_loop_context_compacted_summary_default_none():
    ctx = LoopContext(task="hello")
    assert ctx.compacted_summary is None


def test_loop_context_group_count():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "First message")
    ctx.add_message("assistant", "Response")
    assert ctx.group_count >= 2


def test_loop_context_group_count_with_tool_group():
    ctx = LoopContext(task="hello")
    ctx.add_message("user", "Read file")
    ctx.add_message(
        "assistant",
        "Will read",
        tool_calls=[{"id": "c1", "name": "read_file", "arguments": {}}],
    )
    ctx.add_message("tool", "file contents", tool_call_id="c1")
    assert ctx.group_count >= 2


def test_midrun_compress_system_prompt():
    pm = PromptManager()
    prompt = pm.get_midrun_compression_system_prompt()
    assert "User's original intent" in prompt
    assert "Operations performed" in prompt
    assert "session_recall can retrieve" in prompt


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
    messages = builder.build(ctx, tools=[])
    user_contents = [m.content for m in messages if m.role == MessageRole.USER]
    assert any("Fix the login bug" in c for c in user_contents if c)


def test_task_anchor_not_duplicated_in_recent():
    builder = _make_builder()
    ctx = LoopContext(task="Fix the login bug")
    ctx.add_message("user", "Fix the login bug")
    ctx.add_message("assistant", "I will investigate")
    messages = builder.build(ctx, tools=[])
    task_count = sum(
        1
        for m in messages
        if m.role == MessageRole.USER and m.content == "Fix the login bug"
    )
    assert task_count == 1


def test_compacted_summary_injected():
    builder = _make_builder()
    ctx = LoopContext(task="Fix bug")
    ctx.compacted_summary = "User's original intent: Fix bug\nOperations performed: read foo.py"
    ctx.add_message("user", "Fix bug")
    ctx.add_message("assistant", "Working on it")
    messages = builder.build(ctx, tools=[])
    system_contents = [
        m.content for m in messages
        if m.role == MessageRole.SYSTEM and m.content
    ]
    assert any("Compacted historical context" in c for c in system_contents if c)


def test_tier2_messages_with_tool_output_truncation():
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
    messages = builder.build(ctx, tools=[])
    tool_messages = [
        m for m in messages
        if m.role == MessageRole.SYSTEM and m.content and "truncated" in m.content
    ]
    assert len(tool_messages) > 0


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
                {"id": f"c{i}", "name": "read_file", "arguments": {"path": f"src/{i}.py"}}
            ],
        )
        ctx.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")

    messages = builder.build(ctx, tools=[])

    has_task_anchor = any(
        m.role == MessageRole.USER and m.content == task
        for m in messages
    )
    assert has_task_anchor

    has_tier2_truncated = any(
        m.role == MessageRole.SYSTEM and m.content and "truncated" in m.content
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

    messages = builder.build(ctx, tools=[])
    anchor = next(
        (m for m in messages if m.role == MessageRole.USER and "SSO" in (m.content or "")),
        None,
    )
    assert anchor is not None
    assert "auth.py line 42" in anchor.content
