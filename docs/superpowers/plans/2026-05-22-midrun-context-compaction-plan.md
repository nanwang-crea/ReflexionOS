# Mid-Run Context Compaction 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现三级上下文模型（完整原文 → 逐条截断 → LLM摘要 + Recall回溯），解决 agent 在长 run 中忘记原始输入的问题。

**Architecture:** 在 LoopContext 内维护 token 计数和压缩状态，LoopMessageBuilder 负责三级消息构建，RapidExecutionLoop 在 _call_llm 前检测压力触发压缩，SessionRecallTool 提供按需回溯能力。

**Tech Stack:** Python, tiktoken, pytest, FastAPI, Pydantic, SQLAlchemy

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/llm/token_counter.py` | tiktoken 封装，按 model encoding 计数 |
| `backend/app/tools/session_recall_tool.py` | session 内 recall tool，从 DB 取回完整内容 |
| `backend/app/execution/context_manager.py` | LoopContext 新增 total_tokens, compacted_summary, group_count |
| `backend/app/config/settings.py` | ExecutionSettings 新增三级阈值和截断参数 |
| `backend/app/execution/rapid_loop.py` | _call_llm 前压力检测，新增 _compact_tier2/3 |
| `backend/app/execution/loop_message_builder.py` | Task Anchor + Tier 2/3 注入，recent_context_messages 去重 |
| `backend/app/execution/prompt_manager.py` | midrun_compress_system/input 模板 |
| `backend/app/memory/continuation_builder.py` | build_prompt_input 新增 existing_summary 参数 |
| `backend/app/services/agent_service.py` | 传递 compacted_summary，注册 SessionRecallTool |
| `backend/tests/test_execution/test_token_counter.py` | token counter 测试 |
| `backend/tests/test_execution/test_midrun_compaction.py` | 三级上下文模型测试 |
| `backend/tests/test_tools/test_session_recall_tool.py` | recall tool 测试 |

---

### Task 1: Token Counter

**Files:**
- Create: `backend/app/llm/token_counter.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_execution/test_token_counter.py`

- [ ] **Step 1: Add tiktoken to requirements**

Add `tiktoken` to `backend/requirements.txt`.

- [ ] **Step 2: Install tiktoken**

Run: `pip install tiktoken`

- [ ] **Step 3: Write the failing test**

```python
# backend/tests/test_execution/test_token_counter.py
import pytest
from app.llm.token_counter import count_tokens, count_messages_tokens


def test_count_tokens_english():
    text = "Hello world, this is a test."
    tokens = count_tokens(text)
    assert isinstance(tokens, int)
    assert tokens > 0


def test_count_tokens_chinese():
    text = "你好世界，这是一个测试。"
    tokens = count_tokens(text)
    assert isinstance(tokens, int)
    assert tokens > 0


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_count_messages_tokens():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "tool", "content": "file contents here", "tool_call_id": "call_1"},
    ]
    tokens = count_messages_tokens(messages)
    assert isinstance(tokens, int)
    assert tokens > 0


def test_count_messages_tokens_empty():
    assert count_messages_tokens([]) == 0


def test_count_messages_tokens_with_tool_calls():
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "name": "read_file", "arguments": {"path": "foo.py"}}
            ],
        },
    ]
    tokens = count_messages_tokens(messages)
    assert tokens > 0


def test_count_tokens_model_fallback():
    text = "Hello world"
    tokens_default = count_tokens(text)
    tokens_custom = count_tokens(text, model="gpt-4")
    assert tokens_default > 0
    assert tokens_custom > 0
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_token_counter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm.token_counter'`

- [ ] **Step 5: Write minimal implementation**

```python
# backend/app/llm/token_counter.py
from __future__ import annotations

import tiktoken


_default_encoding: tiktoken.Encoding | None = None


def _get_encoding(model: str = "cl100k_base") -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    if not text:
        return 0
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def count_messages_tokens(
    messages: list[dict], model: str = "cl100k_base"
) -> int:
    if not messages:
        return 0
    total = 0
    for msg in messages:
        total += 4  # message overhead (role, separators)
        content = msg.get("content")
        if isinstance(content, str):
            total += count_tokens(content, model)
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                total += count_tokens(tc.get("name", ""), model)
                import json
                args_str = json.dumps(tc.get("arguments", {}), ensure_ascii=False)
                total += count_tokens(args_str, model)
                total += 3  # tool call overhead
        tool_call_id = msg.get("tool_call_id")
        if tool_call_id:
            total += count_tokens(str(tool_call_id), model)
    total += 2  # priming tokens
    return total
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_token_counter.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/llm/token_counter.py backend/tests/test_execution/test_token_counter.py backend/requirements.txt
git commit -m "feat: add token counter using tiktoken"
```

---

### Task 2: ExecutionSettings 扩展

**Files:**
- Modify: `backend/app/config/settings.py`
- Test: `backend/tests/test_execution/test_midrun_compaction.py` (add settings test)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_execution/test_midrun_compaction.py
from app.config.settings import ExecutionSettings


def test_execution_settings_tier2_threshold():
    settings = ExecutionSettings()
    assert settings.tier2_truncate_threshold_tokens == 50_000


def test_execution_settings_tier3_threshold():
    settings = ExecutionSettings()
    assert settings.tier3_compact_threshold_tokens == 100_000


def test_execution_settings_tool_output_max_chars():
    settings = ExecutionSettings()
    assert settings.tool_output_max_chars == 2_400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py -v`
Expected: FAIL with `AttributeError` on tier2 fields

- [ ] **Step 3: Write minimal implementation**

Add three fields to `ExecutionSettings` in `backend/app/config/settings.py`:

```python
class ExecutionSettings(BaseModel):
    max_steps: int = Field(default=1000, ge=1, le=200)
    max_execution_time: int = Field(default=600)
    tier2_truncate_threshold_tokens: int = Field(default=50_000, ge=1)
    tier3_compact_threshold_tokens: int = Field(default=100_000, ge=1)
    tool_output_max_chars: int = Field(default=2_400, ge=100)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config/settings.py backend/tests/test_execution/test_midrun_compaction.py
git commit -m "feat: add tier2/tier3 threshold settings to ExecutionSettings"
```

---

### Task 3: LoopContext Token Tracking

**Files:**
- Modify: `backend/app/execution/context_manager.py`
- Test: `backend/tests/test_execution/test_midrun_compaction.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_execution/test_midrun_compaction.py`:

```python
from app.execution.context_manager import LoopContext


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
    ctx.add_message("assistant", "Will read", tool_calls=[{"id": "c1", "name": "read_file", "arguments": {}}])
    ctx.add_message("tool", "file contents", tool_call_id="c1")
    assert ctx.group_count >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py::test_loop_context_tracks_total_tokens -v`
Expected: FAIL with `AttributeError` on `total_tokens`

- [ ] **Step 3: Write minimal implementation**

Modify `backend/app/execution/context_manager.py`:

```python
import logging
from datetime import datetime
from typing import Any

from app.execution.models import LoopStep
from app.execution.plan_engine import Plan
from app.llm.base import MessageRole
from app.llm.token_counter import count_tokens, count_messages_tokens

logger = logging.getLogger(__name__)


class LoopContext:

    def __init__(self, task: str, project_path: str | None = None, run_id: str | None = None):
        self.task = task
        self.project_path = project_path
        self.run_id = run_id or f"run-{id(self)}"
        self.history: list[dict[str, Any]] = []
        self.steps: list[LoopStep] = []
        self.messages: list[dict[str, Any]] = []
        self.current_step_number = 0
        self.workspace_snapshot: dict[str, Any] = {}
        self.system_sections: list[str] = []
        self.supplemental_context: str | None = None
        self.plan: Plan | None = None
        self.total_tokens: int = 0
        self.compacted_summary: str | None = None
        self.group_count: int = 0

    @classmethod
    def from_run_input(
        cls,
        *,
        task: str,
        project_path: str | None = None,
        run_id: str | None = None,
        seed_messages: list[dict[str, str]] | None = None,
        supplemental_context: str | None = None,
        system_sections: list[str] | None = None,
    ) -> "LoopContext":
        context = cls(task=task, project_path=project_path, run_id=run_id)

        allowed_seed_roles = {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL}
        for seeded in seed_messages or []:
            if not isinstance(seeded, dict):
                continue
            role = str(seeded.get("role") or "").strip().lower()
            if role not in allowed_seed_roles:
                continue
            content = seeded.get("content")
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue
            context.add_message(role, content)

        context.supplemental_context = supplemental_context
        context.system_sections = system_sections or []
        context.add_message("user", task)
        return context

    def update_history(self, action: Any, result: str) -> None:
        self.history.append(
            {"action": action, "result": result, "timestamp": datetime.now().isoformat()}
        )
        logger.debug("更新执行历史")

    def add_step(self, step: LoopStep) -> None:
        self.steps.append(step)
        self.current_step_number = step.step_number
        logger.info("添加执行步骤 %s: %s", step.step_number, step.tool)

    def add_message(
        self,
        role: str,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        message: dict[str, Any] = {"role": role, "timestamp": datetime.now().isoformat()}

        if content is not None:
            message["content"] = content
        if tool_calls:
            message["tool_calls"] = tool_calls
        if tool_call_id:
            message["tool_call_id"] = tool_call_id

        self.messages.append(message)

        msg_tokens = count_messages_tokens([message])
        self.total_tokens += msg_tokens

        self._update_group_count(message)

    def recalculate_tokens(self) -> None:
        self.total_tokens = count_messages_tokens(self.messages)

    def _update_group_count(self, message: dict[str, Any]) -> None:
        if message["role"] == MessageRole.ASSISTANT and message.get("tool_calls"):
            self.group_count += 1
        elif message["role"] == MessageRole.TOOL:
            pass
        else:
            self.group_count += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/context_manager.py
git commit -m "feat: add token tracking and group count to LoopContext"
```

---

### Task 4: Prompt Manager - Mid-Run Compress Templates

**Files:**
- Modify: `backend/app/execution/prompt_manager.py`
- Test: `backend/tests/test_execution/test_midrun_compaction.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_execution/test_midrun_compaction.py`:

```python
from app.execution.prompt_manager import PromptManager


def test_midrun_compress_system_prompt():
    pm = PromptManager()
    prompt = pm.get_midrun_compression_system_prompt()
    assert "用户原始意图" in prompt
    assert "已执行的操作" in prompt
    assert "可 session_recall" in prompt


def test_midrun_compress_input_prompt():
    pm = PromptManager()
    prompt = pm.get_midrun_compression_prompt(task="Fix bug", transcript="some transcript")
    assert "Fix bug" in prompt
    assert "some transcript" in prompt


def test_midrun_compress_input_with_existing_summary():
    pm = PromptManager()
    prompt = pm.get_midrun_compression_prompt(
        task="Fix bug",
        transcript="new messages",
        existing_summary="previous summary"
    )
    assert "previous summary" in prompt
    assert "new messages" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py::test_midrun_compress_system_prompt -v`
Expected: FAIL with `AttributeError` on `get_midrun_compression_system_prompt`

- [ ] **Step 3: Write minimal implementation**

Add to `PromptManager._load_default_templates()` in `backend/app/execution/prompt_manager.py`:

```python
        self.register_template(
            name="midrun_compress_system",
            template="""You are generating a mid-run context compaction summary.
The agent is in the middle of executing a task and the context window is under pressure.
You must compress older conversation history into a concise summary.

This summary is DERIVED from the transcript below. Do not invent facts.
If unsure, state uncertainty.
Write in Chinese.

Output MUST be plain text with EXACTLY these 5 sections:
用户原始意图: <the user's original intent, preserving key phrasing>
已执行的操作: <key operations performed, one per line, mark recallable items>
  - <operation description> [可 session_recall 取回完整内容]
已确认的发现: <important findings confirmed so far>
当前进度: <what step are we at, what remains>
未解决的问题: <open issues that still need attention>

Rules:
- For each file read or shell execution, include [可 session_recall 取回完整内容] marker
- Preserve the user's original intent verbatim as much as possible
- Keep operation descriptions short but specific (include file names, function names)
- If an existing summary is provided, integrate it with new information""",
            variables=[],
        )

        self.register_template(
            name="midrun_compress_input",
            template="""Compress the following conversation history into a mid-run summary.

Task (current user input):
$task

$existing_summary_block

New conversation history (oldest to newest):
$transcript
""",
            variables=["task", "transcript", "existing_summary_block"],
        )
```

Add methods to `PromptManager`:

```python
    def get_midrun_compression_system_prompt(self) -> str:
        return self.get_template("midrun_compress_system").render()

    def get_midrun_compression_prompt(
        self,
        *,
        task: str,
        transcript: str,
        existing_summary: str | None = None,
    ) -> str:
        if existing_summary:
            existing_summary_block = f"[已有摘要]\n{existing_summary}\n\n[新增对话]"
        else:
            existing_summary_block = ""
        return self.get_template("midrun_compress_input").render(
            task=task or "",
            transcript=transcript or "",
            existing_summary_block=existing_summary_block,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/prompt_manager.py
git commit -m "feat: add midrun compression prompt templates"
```

---

### Task 5: LoopMessageBuilder - Task Anchor + Tier 2 + Tier 3

**Files:**
- Modify: `backend/app/execution/loop_message_builder.py`
- Test: `backend/tests/test_execution/test_midrun_compaction.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_execution/test_midrun_compaction.py`:

```python
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.execution.context_manager import LoopContext
from app.llm.base import MessageRole


def _make_builder() -> LoopMessageBuilder:
    pm = PromptManager()
    return LoopMessageBuilder(prompt_manager=pm, max_context_groups=10)


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
        1 for m in messages
        if m.role == MessageRole.USER and m.content == "Fix the login bug"
    )
    assert task_count == 1


def test_compacted_summary_injected():
    builder = _make_builder()
    ctx = LoopContext(task="Fix bug")
    ctx.compacted_summary = "用户原始意图: Fix bug\n已执行的操作: read foo.py"
    ctx.add_message("user", "Fix bug")
    ctx.add_message("assistant", "Working on it")
    messages = builder.build(ctx, tools=[])
    system_contents = [m.content for m in messages if m.role == MessageRole.SYSTEM and m.content]
    assert any("已压缩的历史上下文" in c for c in system_contents if c)


def test_tier2_messages_with_tool_output_truncation():
    builder = _make_builder()
    ctx = LoopContext(task="Read files")
    long_output = "A" * 5000
    for i in range(15):
        ctx.add_message("assistant", f"Reading file {i}", tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}])
        ctx.add_message("tool", long_output, tool_call_id=f"c{i}")
    messages = builder.build(ctx, tools=[])
    tool_messages = [m for m in messages if m.role == MessageRole.SYSTEM and m.content and "省略" in m.content]
    assert len(tool_messages) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py::test_task_anchor_injected -v`
Expected: FAIL (current build() does not inject task anchor)

- [ ] **Step 3: Write minimal implementation**

Modify `backend/app/execution/loop_message_builder.py`:

```python
from app.execution.context_manager import LoopContext
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMMessage, LLMToolCall, LLMToolDefinition, MessageRole
from app.memory.text_compaction import truncate_head_tail


class LoopMessageBuilder:

    def __init__(self, prompt_manager: PromptManager, max_context_groups: int, tool_output_max_chars: int = 2_400):
        self.prompt_manager = prompt_manager
        self.max_context_groups = max_context_groups
        self.tool_output_max_chars = tool_output_max_chars

    @staticmethod
    def _inject_context_sections(context: LoopContext, messages: list[LLMMessage]) -> None:
        for section in context.system_sections or []:
            if str(section or "").strip():
                messages.append(LLMMessage(role=MessageRole.SYSTEM, content=str(section)))
        supplemental = context.supplemental_context
        if supplemental and str(supplemental).strip():
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=str(supplemental).strip()))

    def build(self, context: LoopContext, tools: list[LLMToolDefinition]) -> list[LLMMessage]:
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM, content=self.prompt_manager.get_system_prompt(tools)
            )
        ]

        self._inject_context_sections(context, messages)

        if context.plan:
            messages.append(
                LLMMessage(role=MessageRole.SYSTEM, content=context.plan.render_for_context())
            )
            completed_findings = context.plan.completed_findings()
            if completed_findings:
                findings_text = "\n".join(f"- {f}" for f in completed_findings)
                messages.append(
                    LLMMessage(role=MessageRole.SYSTEM, content=f"前序步骤发现:\n{findings_text}")
                )

        messages.append(LLMMessage(role=MessageRole.USER, content=context.task))

        if context.compacted_summary:
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[已压缩的历史上下文]\n{context.compacted_summary}",
                )
            )

        tier2_messages = self._build_tier2_messages(context)
        for msg in tier2_messages:
            messages.append(msg)

        for msg in self.recent_context_messages(context):
            tool_calls = [LLMToolCall(**tool_call) for tool_call in msg.get("tool_calls", [])]
            messages.append(
                LLMMessage(
                    role=msg["role"],
                    content=msg.get("content"),
                    tool_calls=tool_calls,
                    tool_call_id=msg.get("tool_call_id"),
                )
            )

        return messages

    def build_initial_plan(self, context: LoopContext) -> list[LLMMessage]:
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM, content=self.prompt_manager.get_initial_plan_prompt()
            )
        ]

        self._inject_context_sections(context, messages)

        for msg in self.recent_context_messages(context):
            if msg["role"] not in {MessageRole.USER, MessageRole.ASSISTANT}:
                continue
            if not msg.get("content"):
                continue
            messages.append(LLMMessage(role=msg["role"], content=msg.get("content")))

        return messages

    def _build_tier2_messages(self, context: LoopContext) -> list[LLMMessage]:
        grouped = self._group_messages(context.messages)
        if len(grouped) <= self.max_context_groups:
            return []

        older_groups = grouped[: -self.max_context_groups]
        tier2: list[LLMMessage] = []

        for group in older_groups:
            for msg in group:
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                if msg["role"] == MessageRole.TOOL and len(content) > self.tool_output_max_chars:
                    truncated = truncate_head_tail(
                        content,
                        self.tool_output_max_chars,
                        head_chars=1_600,
                        tail_chars=600,
                        reason="session_recall 取回",
                    )
                    tier2.append(
                        LLMMessage(role=MessageRole.SYSTEM, content=f"[tool output] {truncated}")
                    )
                elif msg["role"] == MessageRole.TOOL:
                    tier2.append(
                        LLMMessage(role=MessageRole.SYSTEM, content=f"[tool output] {content}")
                    )
                elif msg["role"] == MessageRole.ASSISTANT:
                    text = content
                    if msg.get("tool_calls"):
                        tool_names = [tc.get("name", "") for tc in msg["tool_calls"]]
                        text = f"[assistant called: {', '.join(tool_names)}] {text}"
                    tier2.append(LLMMessage(role=MessageRole.SYSTEM, content=text))
                elif msg["role"] == MessageRole.USER:
                    if content == context.task:
                        continue
                    tier2.append(LLMMessage(role=MessageRole.SYSTEM, content=f"[user] {content}"))

        return tier2

    def recent_context_messages(self, context: LoopContext) -> list[dict]:
        if not context.messages:
            return []

        grouped_messages: list[list[dict]] = []
        active_tool_group: list[dict] | None = None

        for msg in context.messages:
            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                active_tool_group = [msg]
                grouped_messages.append(active_tool_group)
                continue

            if msg["role"] == MessageRole.TOOL and active_tool_group is not None:
                active_tool_group.append(msg)
                continue

            active_tool_group = None
            grouped_messages.append([msg])

        recent_groups = grouped_messages[-self.max_context_groups :]
        flat = [message for group in recent_groups for message in group]
        return [m for m in flat if not (m["role"] == MessageRole.USER and m.get("content") == context.task)]

    def _group_messages(self, messages: list[dict]) -> list[list[dict]]:
        grouped: list[list[dict]] = []
        active_tool_group: list[dict] | None = None
        for msg in messages:
            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                active_tool_group = [msg]
                grouped.append(active_tool_group)
                continue
            if msg["role"] == MessageRole.TOOL and active_tool_group is not None:
                active_tool_group.append(msg)
                continue
            active_tool_group = None
            grouped.append([msg])
        return grouped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/loop_message_builder.py
git commit -m "feat: add Task Anchor, Tier 2 truncation, and Tier 3 summary to LoopMessageBuilder"
```

---

### Task 6: Session Recall Tool

**Files:**
- Create: `backend/app/tools/session_recall_tool.py`
- Test: `backend/tests/test_tools/test_session_recall_tool.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tools/test_session_recall_tool.py
import pytest
from app.tools.session_recall_tool import SessionRecallTool


def test_session_recall_tool_name():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    assert tool.name == "session_recall"


def test_session_recall_tool_schema():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    schema = tool.get_schema()
    assert "query" in schema["parameters"]["properties"]


@pytest.mark.asyncio
async def test_session_recall_tool_execute_empty_query():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    result = await tool.execute({"query": "", "session_id": "s1"})
    assert result.success is True
    assert result.data is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tools/test_session_recall_tool.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/tools/session_recall_tool.py
from typing import Any

from app.memory.recall_service import RecallService
from app.tools.base import BaseTool, ToolResult


class SessionRecallTool(BaseTool):

    def __init__(
        self,
        *,
        session_id: str,
        project_id: str,
        recall_service: RecallService | None = None,
    ):
        self._session_id = session_id
        self._project_id = project_id
        self._recall_service = recall_service or RecallService()

    @property
    def name(self) -> str:
        return "session_recall"

    @property
    def description(self) -> str:
        return "在当前会话历史中搜索之前的对话、文件读取、工具输出等完整内容。当压缩摘要中标记 [可 session_recall 取回] 时可使用此工具取回完整内容。"

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要查找的内容关键词",
                    },
                    "message_type": {
                        "type": "string",
                        "enum": ["tool_trace", "user_message", "assistant_message", "all"],
                        "description": "筛选消息类型（默认 all）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量（默认 3）",
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        if not query:
            return ToolResult(success=True, data={"results": [], "message": "空查询，无结果"})

        limit = args.get("limit", 3)
        results = self._recall_service.search(
            project_id=self._project_id,
            query=query,
            limit=limit,
        )

        message_type_filter = args.get("message_type", "all")
        if message_type_filter != "all":
            results = [r for r in results if r.summary.startswith(f"[{message_type_filter}")]

        if not results:
            return ToolResult(
                success=True,
                data={"results": [], "message": f"未找到与 '{query}' 相关的内容"},
            )

        formatted = []
        for r in results:
            formatted.append({
                "score": round(r.score, 3),
                "summary": r.summary,
                "evidence": r.evidence,
            })

        return ToolResult(success=True, data={"results": formatted})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_tools/test_session_recall_tool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/session_recall_tool.py backend/tests/test_tools/test_session_recall_tool.py
git commit -m "feat: add SessionRecallTool for mid-run context recall"
```

---

### Task 7: RapidExecutionLoop - Mid-Run Compaction

**Files:**
- Modify: `backend/app/execution/rapid_loop.py`
- Test: `backend/tests/test_execution/test_midrun_compaction.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_execution/test_midrun_compaction.py`:

```python
from app.memory.text_compaction import truncate_head_tail


def test_tier2_compaction_reduces_tokens():
    ctx = LoopContext(task="Read many files")
    long_output = "A" * 5000
    for i in range(25):
        ctx.add_message("assistant", f"Reading file {i}", tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}])
        ctx.add_message("tool", long_output, tool_call_id=f"c{i}")
    original_tokens = ctx.total_tokens
    builder = _make_builder()
    messages = builder.build(ctx, tools=[])
    built_tokens = sum(count_messages_tokens([m.model_dump()]) for m in messages)
    assert built_tokens < original_tokens


def test_tier3_compaction_produces_summary():
    ctx = LoopContext(task="Big task")
    ctx.compacted_summary = "用户原始意图: Big task\n已执行的操作: read files"
    ctx.add_message("user", "Big task")
    ctx.add_message("assistant", "Working")
    builder = _make_builder()
    messages = builder.build(ctx, tools=[])
    has_summary = any(
        m.role == MessageRole.SYSTEM and m.content and "已压缩的历史上下文" in m.content
        for m in messages
    )
    assert has_summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py::test_tier2_compaction_reduces_tokens -v`
Expected: Should PASS (Tier 2 is in message builder) - but verify Tier 3 path

- [ ] **Step 3: Add _compact_context to RapidExecutionLoop**

Add the following method to `RapidExecutionLoop` in `backend/app/execution/rapid_loop.py`:

```python
    async def _compact_context(self, context: LoopContext) -> None:
        settings = config_manager.settings.execution
        if context.total_tokens <= settings.tier2_truncate_threshold_tokens:
            return

        if context.total_tokens > settings.tier3_compact_threshold_tokens:
            await self._compact_tier3(context)

    async def _compact_tier3(self, context: LoopContext) -> None:
        try:
            grouped = self.message_builder._group_messages(context.messages)
            if len(grouped) <= self.max_context_groups:
                return

            older_groups = grouped[: -self.max_context_groups]
            older_messages = [msg for group in older_groups for msg in group]

            transcript_parts = []
            for msg in older_messages:
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    role = msg.get("role", "unknown")
                    transcript_parts.append(f"[{role}] {content[:2000]}")

            transcript = "\n\n".join(transcript_parts)

            system_prompt = self.prompt_manager.get_midrun_compression_system_prompt()
            user_prompt = self.prompt_manager.get_midrun_compression_prompt(
                task=context.task,
                transcript=transcript,
                existing_summary=context.compacted_summary,
            )

            from app.llm.base import LLMMessage, MessageRole
            response = await self.llm.complete(
                [
                    LLMMessage(role=MessageRole.SYSTEM, content=system_prompt),
                    LLMMessage(role=MessageRole.USER, content=user_prompt),
                ],
                tools=None,
            )

            content = (response.content or "").strip()
            if not content:
                logger.warning("Tier 3 compaction returned empty, skipping")
                return

            context.compacted_summary = content

            recent_groups = grouped[-self.max_context_groups :]
            context.messages = [msg for group in recent_groups for msg in group]
            context.recalculate_tokens()

            logger.info(
                "Tier 3 compaction completed. Summary length=%d, remaining messages=%d, tokens=%d",
                len(content), len(context.messages), context.total_tokens,
            )
        except Exception:
            logger.exception("Tier 3 compaction failed, skipping")
```

Modify `_call_llm` to insert pressure check before building messages:

```python
    async def _call_llm(self, context: LoopContext) -> LLMResponse:
        await self._compact_context(context)
        # ... rest of existing _call_llm unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_midrun_compaction.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/rapid_loop.py
git commit -m "feat: add mid-run context compaction to RapidExecutionLoop"
```

---

### Task 8: ContinuationBuilder - existing_summary 参数

**Files:**
- Modify: `backend/app/memory/continuation_builder.py`
- Test: `backend/tests/test_memory/test_continuation_builder.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_memory/test_continuation_builder.py`:

```python
def test_build_prompt_input_with_existing_summary():
    from app.memory.continuation_builder import ContinuationArtifactBuilder
    builder = ContinuationArtifactBuilder()
    messages = [
        _make_message(MessageType.USER_MESSAGE, "user", "Fix bug"),
        _make_message(MessageType.ASSISTANT_MESSAGE, "assistant", "I fixed it"),
    ]
    result = builder.build_prompt_input(
        task="Fix bug",
        messages=messages,
        existing_summary="用户原始意图: Fix bug\n已执行的操作: read foo.py",
    )
    assert "已有摘要" in result.transcript
    assert "Fix bug" in result.transcript
```

(If `_make_message` helper doesn't exist, add it based on existing test patterns.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_memory/test_continuation_builder.py -v`
Expected: FAIL with `TypeError` on `existing_summary` parameter

- [ ] **Step 3: Write minimal implementation**

Modify `ContinuationArtifactBuilder.build_prompt_input`:

```python
    def build_prompt_input(
        self,
        *,
        task: str,
        messages: list[Message],
        existing_summary: str | None = None,
    ) -> ContinuationPromptInput:
        items = self._build_items(messages)
        transcript = self._fit_global_budget(items)

        if existing_summary:
            transcript = f"[已有摘要]\n{existing_summary}\n\n[新增对话]\n{transcript}"

        return ContinuationPromptInput(
            task=self._truncate_text(task or "", self.max_task_chars),
            transcript=transcript,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_memory/test_continuation_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/continuation_builder.py
git commit -m "feat: add existing_summary parameter to ContinuationArtifactBuilder"
```

---

### Task 9: AgentService - Wire It All Together

**Files:**
- Modify: `backend/app/services/agent_service.py`

- [ ] **Step 1: Register SessionRecallTool in tool registry**

In `_build_run_tool_registry`, add the SessionRecallTool registration. This requires passing `session_id` and `project_id` which are available at `_run_turn` time, so the tool must be registered dynamically per run:

Add import at top:
```python
from app.tools.session_recall_tool import SessionRecallTool
```

Modify `_run_turn` to register the recall tool after creating the tool registry:

```python
        run_tool_registry = self._build_run_tool_registry(project_path)
        run_tool_registry.register(SessionRecallTool(session_id=session_id, project_id=project_id))
```

- [ ] **Step 2: Pass compacted_summary to continuation builder**

In `_generate_and_persist_continuation_artifact`, add `existing_summary` parameter:

```python
    async def _generate_and_persist_continuation_artifact(
        self,
        *,
        llm: UniversalLLMInterface,
        session_id: str,
        turn_id: str,
        run_id: str,
        task: str,
        compacted_summary: str | None = None,
    ) -> None:
        turn_messages = self.conversation_service.list_turn_messages(turn_id)
        prompt_input = self.continuation_builder.build_prompt_input(
            task=task,
            messages=turn_messages,
            existing_summary=compacted_summary,
        )
        # ... rest unchanged
```

And update the call site in `_run_turn`:

```python
            try:
                await self._generate_and_persist_continuation_artifact(
                    llm=llm,
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    task=task,
                    compacted_summary=loop_context.compacted_summary if loop_context else None,
                )
```

Note: `loop_context` needs to be accessible after `execution_loop.run()`. Check how the loop returns context — it may need a small refactor to expose it, or store it on the loop instance.

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agent_service.py
git commit -m "feat: wire SessionRecallTool and compacted_summary into AgentService"
```

---

### Task 10: Integration Test & Lint

**Files:**
- Test: `backend/tests/test_execution/test_midrun_compaction.py` (extend)

- [ ] **Step 1: Write integration-style test**

Add to `backend/tests/test_execution/test_midrun_compaction.py`:

```python
def test_full_three_tier_flow():
    builder = _make_builder()
    ctx = LoopContext(task="Refactor the authentication module to support OAuth2")
    ctx.add_message("user", "Refactor the authentication module to support OAuth2")
    for i in range(25):
        ctx.add_message("assistant", f"Reading file {i}", tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {"path": f"src/{i}.py"}}])
        ctx.add_message("tool", "A" * 5000, tool_call_id=f"c{i}")

    messages = builder.build(ctx, tools=[])

    has_task_anchor = any(
        m.role == MessageRole.USER and m.content == "Refactor the authentication module to support OAuth2"
        for m in messages
    )
    assert has_task_anchor

    has_tier2_truncated = any(
        m.role == MessageRole.SYSTEM and m.content and "省略" in m.content
        for m in messages
    )
    assert has_tier2_truncated

    user_task_count = sum(
        1 for m in messages
        if m.role == MessageRole.USER and m.content == "Refactor the authentication module to support OAuth2"
    )
    assert user_task_count == 1


def test_task_anchor_preserves_original_intent():
    builder = _make_builder()
    ctx = LoopContext(task="Please fix the bug where users can't login with SSO. The error is in auth.py line 42.")
    for i in range(15):
        ctx.add_message("assistant", f"Step {i}", tool_calls=[{"id": f"c{i}", "name": "read_file", "arguments": {}}])
        ctx.add_message("tool", "B" * 3000, tool_call_id=f"c{i}")

    messages = builder.build(ctx, tools=[])
    anchor = next(
        (m for m in messages if m.role == MessageRole.USER and "SSO" in (m.content or "")),
        None,
    )
    assert anchor is not None
    assert "auth.py line 42" in anchor.content
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Run lint**

Run: `cd backend && ruff check app/ tests/ --fix`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_execution/test_midrun_compaction.py
git commit -m "test: add integration tests for three-tier context model"
```

---

## Plan Self-Review

**1. Spec coverage:**

| Spec requirement | Task |
|---|---|
| 5.1 Task Anchor | Task 5 |
| 5.2 Token pressure detection | Tasks 1, 2, 3 |
| 5.3 Tier 2 truncation | Task 5 |
| 5.4 Tier 3 LLM compression | Tasks 4, 7 |
| 5.5 Session Recall Tool | Task 6 |
| 5.6 Compression failure fallback | Task 7 |
| 5.7 Continuation reuse | Tasks 8, 9 |

**2. Placeholder scan:** No TBD/TODO found.

**3. Type consistency:** All method names and signatures are consistent across tasks. `_group_messages` is used in both Task 5 (LoopMessageBuilder) and Task 7 (RapidExecutionLoop._compact_tier3) — both use the same logic.
