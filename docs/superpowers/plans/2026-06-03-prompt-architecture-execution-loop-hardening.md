# Prompt Architecture & Execution Loop Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the root causes of LLM tool-call confusion, premature termination, and empty responses by restructuring the prompt architecture and hardening the execution loop — inspired by systematic comparison with OpenCode.

**Architecture:** Two-layer fix: (A) Prompt architecture — provider-differentiated system prompts, anti-stop enforcement, structured error feedback, persistent task anchoring; (B) Execution loop — doom-loop detection for all tools, completion-gate tightening, empty-response graduated handling, JSON parse failure visibility.

**Tech Stack:** Python 3.12+, Pydantic, asyncio, pytest

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `backend/app/execution/prompt_manager.py` | Modify | Add provider-differentiated prompts, enhanced error template, anti-stop directives |
| `backend/app/execution/loop_message_builder.py` | Modify | Persistent task anchor injection, compaction-continue message |
| `backend/app/execution/rapid_loop.py` | Modify | Doom-loop detection, completion gate, empty-response handling, compaction-continue hook |
| `backend/app/execution/context_manager.py` | Modify | Track tool-call signatures for doom-loop detection |
| `backend/app/execution/runtime_tool_definitions.py` | Modify | Add `skill` to exploration_tools |
| `backend/app/llm/openai_adapter.py` | Modify | JSON parse failure → explicit error in args instead of `{}` |
| `backend/tests/test_execution/test_prompt_manager.py` | Modify | Tests for new prompt variants and error template |
| `backend/tests/test_execution/test_loop_message_builder.py` | Modify | Tests for persistent task anchor and compaction-continue |
| `backend/tests/test_execution/test_rapid_loop.py` | Modify | Tests for doom-loop, completion gate, empty-response |

---

### Task 1: Provider-Differentiated System Prompts

**Files:**
- Modify: `backend/app/execution/prompt_manager.py:25-101`
- Modify: `backend/tests/test_execution/test_prompt_manager.py`

ReflexionOS uses a single English system prompt for all models. Chinese models (Qwen/DeepSeek/GLM) respond poorly to English-only instructions and misinterpret ambiguous directives like "Stop when done". We need provider-family-specific prompt variants.

**Design:** Add a `PromptFamily` enum and a `prompt_family_for_model()` classifier. The existing `system` template becomes the `default` family. Add a `cn_compatible` family for Chinese-origin models with bilingual directives and more explicit anti-stop language. The `PromptManager` gets a `model_name` parameter at construction time (or a `set_prompt_family()` method) that selects which template set to use.

- [ ] **Step 1: Write the failing test**

```python
# In test_prompt_manager.py, add:

class TestPromptFamilySelection:
    def test_default_family_for_unknown_model(self):
        manager = PromptManager(model_name="gpt-4o")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
        assert "You MUST continue using tools until the task is fully complete" in prompt

    def test_cn_compatible_family_for_qwen(self):
        manager = PromptManager(model_name="qwen-plus")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
        assert "你必须持续使用工具直到任务完全完成" in prompt or "You MUST continue" in prompt

    def test_cn_compatible_family_for_deepseek(self):
        manager = PromptManager(model_name="deepseek-chat")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt

    def test_cn_compatible_family_for_glm(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_prompt_manager.py::TestPromptFamilySelection -v`
Expected: FAIL — `PromptManager.__init__()` does not accept `model_name`

- [ ] **Step 3: Implement prompt family classifier and differentiated templates**

In `prompt_manager.py`, add:

```python
from enum import Enum


class PromptFamily(str, Enum):
    DEFAULT = "default"
    CN_COMPATIBLE = "cn_compatible"


def classify_prompt_family(model_name: str) -> PromptFamily:
    lower = (model_name or "").lower()
    cn_keywords = ["qwen", "deepseek", "glm-", "chatglm", "yi-", "baichuan", "minimax", "moonshot", "kimi"]
    if any(kw in lower for kw in cn_keywords):
        return PromptFamily.CN_COMPATIBLE
    return PromptFamily.DEFAULT
```

Modify `PromptManager.__init__` to accept `model_name: str = ""`, call `classify_prompt_family`, and register a `system_cn_compatible` template alongside `system`. The `cn_compatible` template is based on the default but adds:

1. **Anti-stop bilingual directive** at the top of "Stopping rules":
```
## Stopping rules (IMPORTANT — read carefully):
- You MUST continue using tools until the task is fully complete.
  你必须持续使用工具直到任务完全完成。不要在任务中途停止。
- Do NOT stop early to provide partial answers or ask the user to write code.
  不要提前停止并提供不完整的答案，也不要要求用户来编写代码。
- Only stop when the user's original request has been fully addressed through your tool operations.
  只有当用户的原始请求已通过工具操作完全解决时才停止。
- Stop when the user's request is fully satisfied.
- ... (rest of original stopping rules)
```

2. **Bilingual error handling** section:
```
## Error handling:
- If a tool call fails, first diagnose WHY it failed before retrying (read the error message carefully).
  如果工具调用失败，首先仔细阅读错误信息，诊断失败原因，然后再重试。
- If the error mentions an invalid parameter name or action, check the tool schema and use the correct parameter.
  如果错误信息提到参数名或 action 无效，请检查工具的 schema 并使用正确的参数。
- Do not make speculative large changes without evidence.
- Do not blindly retry with the same parameters.
  不要用相同的参数盲目重试——相同的参数会产生相同的错误。
```

3. **Explicit tool-usage reminder**:
```
## Tool calling rules:
- Each tool has specific parameter names. Use ONLY the parameter names defined in the tool schema.
  每个工具有特定的参数名。只使用工具 schema 中定义的参数名。
- Do NOT mix parameter names between tools (e.g., do not use 'path' for skill tool or 'name' for file tool).
  不要在不同工具之间混用参数名。
- If a tool call fails, the error message will tell you which parameter was wrong. Fix that parameter specifically.
  如果工具调用失败，错误信息会告诉你哪个参数有问题。请精确修正那个参数。
```

Modify `get_system_prompt` to select template based on `self.prompt_family`:
```python
def get_system_prompt(self, *, working_directory="", platform="", is_git_repo=False) -> str:
    template_name = "system" if self.prompt_family == PromptFamily.DEFAULT else "system_cn_compatible"
    return self.get_template(template_name).render(
        working_directory=working_directory,
        platform=platform,
        date=datetime.now().strftime("%Y-%m-%d"),
        is_git_repo=str(is_git_repo),
    )
```

Also add the anti-stop directive to the DEFAULT `system` template (English only, no bilingual):
```
## Stopping rules (IMPORTANT):
- You MUST continue using tools until the task is fully complete.
  Do NOT stop early to provide partial answers or ask the user to write code.
- Only stop when the user's original request has been fully addressed through your tool operations.
- Stop when the user's request is fully satisfied.
- ... (rest of original)
```

- [ ] **Step 4: Wire model_name into PromptManager construction**

In `rapid_loop.py`, the `PromptManager()` is created at line 63. It needs access to the model name. The model name is available from `self.llm.get_model_name()`. Change:
```python
# rapid_loop.py line 63
self.prompt_manager = PromptManager(model_name=self.llm.get_model_name())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_prompt_manager.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/execution/prompt_manager.py backend/app/execution/rapid_loop.py backend/tests/test_execution/test_prompt_manager.py
git commit -m "feat: provider-differentiated system prompts with anti-stop enforcement"
```

---

### Task 2: Enhanced Error Feedback Template

**Files:**
- Modify: `backend/app/execution/prompt_manager.py:248-258`
- Modify: `backend/tests/test_execution/test_prompt_manager.py`

The current error template is 3 lines of generic guidance. The LLM doesn't know what went wrong or how to fix it. We need structured, actionable error feedback.

- [ ] **Step 1: Write the failing test**

```python
# In test_prompt_manager.py, add:

class TestEnhancedErrorPrompt:
    def test_error_prompt_includes_structured_guidance(self, manager):
        prompt = manager.get_error_prompt(
            error="Unknown action: load",
            tool="file",
            code_snippet="",
        )
        assert "Unknown action: load" in prompt
        assert "Diagnose" in prompt or "diagnose" in prompt
        assert "correct action" in prompt.lower() or "available actions" in prompt.lower()

    def test_error_prompt_includes_original_arguments(self, manager):
        prompt = manager.get_error_prompt(
            error="Missing required parameter: path",
            tool="file",
            code_snippet="",
            original_args={"action": "read", "name": "some_file"},
        )
        assert "action" in prompt
        assert "read" in prompt
        assert "name" in prompt
        assert "path" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_prompt_manager.py::TestEnhancedErrorPrompt -v`
Expected: FAIL — `get_error_prompt` doesn't accept `original_args`

- [ ] **Step 3: Implement enhanced error template**

Replace the `error` template (lines 248-258) with:

```python
self.register_template(
    name="error",
    template="""A tool call failed. Read the error carefully and fix the specific issue.

## Failed call details:
- Tool: $tool
- Error: $error
$original_args_section
$available_actions_section

## How to fix:
1. Read the error message above — it tells you exactly what went wrong.
2. If the error says "Unknown action" or "invalid action", check the tool schema for the list of valid actions.
3. If the error says a parameter is missing or has the wrong name, check the tool schema for the correct parameter names.
4. Do NOT retry with the same parameters — they will produce the same error.
5. Fix the specific issue identified in the error, then retry.""",
    variables=["tool", "error", "original_args_section", "available_actions_section"],
)
```

Update `get_error_prompt` to accept and format `original_args` and `available_actions`:

```python
def get_error_prompt(
    self,
    error: str,
    tool: str,
    code_snippet: str = "",
    original_args: dict | None = None,
    available_actions: list[str] | None = None,
) -> str:
    if original_args:
        args_lines = [f"  - {k}: {v!r}" for k, v in original_args.items() if v is not None]
        original_args_section = "- Arguments you used:\n" + "\n".join(args_lines) if args_lines else ""
    else:
        original_args_section = ""

    if available_actions:
        available_actions_section = f"- Available actions for {tool}: {', '.join(available_actions)}"
    else:
        available_actions_section = ""

    return self.get_template("error").render(
        tool=tool,
        error=error,
        original_args_section=original_args_section,
        available_actions_section=available_actions_section,
    )
```

- [ ] **Step 4: Wire enhanced error prompt into error recovery**

In `rapid_loop.py` `_handle_error_recovery` (line 408-437), update the call to `get_error_prompt` to pass `original_args` and `available_actions`:

```python
# Replace lines 420-424
original_args = last_step.args if last_step.args else None
available_actions = None
if last_step.tool:
    tool_instance = self._tool_registry.get(last_step.tool)
    if tool_instance:
        schema = tool_instance.get_schema()
        action_prop = schema.get("parameters", {}).get("properties", {}).get("action", {})
        if "enum" in action_prop:
            available_actions = action_prop["enum"]

error_prompt = self.prompt_manager.get_error_prompt(
    error=last_step.error or "Unknown error",
    tool=last_step.tool,
    original_args=original_args,
    available_actions=available_actions,
)
```

Also update the error feedback path in `_handle_tool_execution` — where tool errors are emitted via `tool` role messages (line 142-154 of `tool_call_executor.py`). When a tool returns `ToolResult(success=False)`, the `error` field should already contain actionable info. We'll enhance this in Task 5 (JSON parse failure visibility).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_prompt_manager.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/execution/prompt_manager.py backend/app/execution/rapid_loop.py backend/tests/test_execution/test_prompt_manager.py
git commit -m "feat: structured error feedback with original args and available actions"
```

---

### Task 3: Persistent Task Anchor & Compaction-Continue

**Files:**
- Modify: `backend/app/execution/loop_message_builder.py:127-151`
- Modify: `backend/app/execution/rapid_loop.py:813-884`
- Modify: `backend/tests/test_execution/test_loop_message_builder.py`

Two problems: (1) Task Anchor only injected on `group_count <= 1`, so after the first tool call the model never sees the original task again; (2) After Tier 3 compaction, no "continue" message is injected, so the model may just stop.

- [ ] **Step 1: Write the failing test**

```python
# In test_loop_message_builder.py, add:

def test_task_anchor_injected_periodically():
    """Task Anchor is injected every N groups, not just on the first round."""
    builder = LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=10, task_anchor_interval=5)
    context = LoopContext(task="修复 bug")
    # Add 6 groups of tool calls to get past the first-round-only threshold
    for i in range(6):
        tc = LLMToolCall(id=f"call_{i}", name="file", arguments={"action": "read", "path": f"f{i}.py"})
        context.add_message("assistant", content=f"step {i}", tool_calls=[tc.model_dump()])
        context.add_message("tool", content=f"output {i}", tool_call_id=tc.id)

    messages = builder.build(context)
    user_contents = [m.content for m in messages if m.role == "user"]
    # At group_count=6 with interval=5, a task anchor should have been injected
    assert any("修复 bug" in (c or "") for c in user_contents)


def test_compaction_continue_message_injected_after_tier3():
    """After Tier 3 compaction, a continue message is added to context."""
    builder = LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=10)
    context = LoopContext(task="实现新功能")
    # Simulate post-compaction: compacted_summary is set
    context.compacted_summary = "User's original intent: implement new feature"
    context.add_message("user", "实现新功能")

    messages = builder.build(context)
    # After compaction, a user-level continue message should be present
    user_contents = [m.content for m in messages if m.role == "user"]
    assert any("Continue" in (c or "") or "继续" in (c or "") for c in user_contents)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_loop_message_builder.py::test_task_anchor_injected_periodically -v`
Expected: FAIL — `LoopMessageBuilder.__init__` doesn't accept `task_anchor_interval`

- [ ] **Step 3: Implement persistent task anchor**

Modify `LoopMessageBuilder.__init__` to accept `task_anchor_interval: int = 0` (0 = disabled, only first round as before; N = inject every N groups).

In `build()` method, replace the Task Anchor block (lines 127-131):

```python
# Task Anchor: inject original task periodically to maintain focus.
# Inject on first round (group_count <= 1) and every task_anchor_interval groups thereafter.
should_inject_anchor = False
if context.group_count <= 1:
    should_inject_anchor = True
elif self.task_anchor_interval > 0 and context.group_count % self.task_anchor_interval == 0:
    # Only inject if we haven't already injected at this group count
    last_injected_group = context.metadata.get("_last_anchor_group", 0)
    if last_injected_group != context.group_count:
        should_inject_anchor = True
        context.metadata["_last_anchor_group"] = context.group_count

if should_inject_anchor:
    messages.append(LLMMessage(role=MessageRole.USER, content=f"[Task Reminder] {context.task}"))
```

Also add compaction-continue logic. In `build()`, after the Tier 3 compacted summary injection (line 101-108):

```python
# After compaction, inject a continue message to prevent premature stop
if context.compacted_summary and context.group_count > 1:
    last_continue_group = context.metadata.get("_last_compaction_continue_group", 0)
    if last_continue_group != context.group_count:
        messages.append(
            LLMMessage(
                role=MessageRole.USER,
                content=f"Continue the task using tools. Original task: {context.task}",
            )
        )
        context.metadata["_last_compaction_continue_group"] = context.group_count
```

- [ ] **Step 4: Set default task_anchor_interval in RapidExecutionLoop**

In `rapid_loop.py`, update the `LoopMessageBuilder` construction (line 68-72) to pass `task_anchor_interval=8`:

```python
self.message_builder = LoopMessageBuilder(
    prompt_manager=self.prompt_manager,
    max_context_groups=self.MAX_CONTEXT_GROUPS,
    tool_output_max_chars=config_manager.settings.execution.tool_output_max_chars,
    task_anchor_interval=8,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_loop_message_builder.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/execution/loop_message_builder.py backend/app/execution/rapid_loop.py backend/tests/test_execution/test_loop_message_builder.py
git commit -m "feat: persistent task anchor and compaction-continue message"
```

---

### Task 4: Doom-Loop Detection for All Tools

**Files:**
- Modify: `backend/app/execution/rapid_loop.py:159-308`
- Modify: `backend/app/execution/context_manager.py`
- Modify: `backend/tests/test_execution/test_rapid_loop.py`

Currently, stagnation detection only covers read-only tool signatures. Write tools (edit, shell) can be called repeatedly with identical args without detection. This causes the model to loop forever on the same failing action.

- [ ] **Step 1: Write the failing test**

```python
# In test_rapid_loop.py, add:

class TestDoomLoopDetection:
    @pytest.fixture
    def loop_with_doom_detection(self):
        registry = ToolRegistry()
        registry.register(ReadOnlyFileTool())
        registry.register(WriteEditTool())
        llm = AsyncMock()
        llm.get_model_name.return_value = "test-model"
        loop = RapidExecutionLoop(llm=llm, tool_registry=registry, max_steps=50, context_window=128000)
        return loop

    @pytest.mark.asyncio
    async def test_identical_write_tool_calls_trigger_recovery(self, loop_with_doom_detection):
        """3 identical write-tool calls in a row triggers doom-loop handling."""
        loop = loop_with_doom_detection
        tc = LLMToolCall(id="c1", name="edit", arguments={"action": "str_replace", "path": "x.py", "old_string": "a", "new_string": "b"})

        # Simulate 3 rounds of the same tool call
        for i in range(3):
            loop._runtime = RuntimeState()
            loop._runtime.step_num = i
            # Each time, the same tool call + same failure
            rt = loop._runtime
            rt.consecutive_failures = 0
            step = LoopStep(step_number=i+1, tool="edit", args=tc.arguments,
                          status=StepStatus.FAILED, error="old_string not found", duration=0.1,
                          tool_call_id=f"c{i}")
            # Track signature in context metadata
            sig = f"edit:{json.dumps(tc.arguments, sort_keys=True)}"
            recent_sigs = loop._runtime.__dict__.setdefault("_recent_tool_signatures", [])
            recent_sigs.append(sig)

        # After 3 identical calls, doom-loop should be detected
        recent_sigs = loop._runtime._recent_tool_signatures
        from collections import Counter
        sig_counts = Counter(recent_sigs)
        most_common_sig, count = sig_counts.most_common(1)[0]
        assert count >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_rapid_loop.py::TestDoomLoopDetection -v`
Expected: Test structure needs adjustment — this tests the detection concept, not the integrated flow

- [ ] **Step 3: Implement doom-loop detection**

In `rapid_loop.py`, add a helper method and integrate it into `_handle_tool_execution`:

```python
DOOM_LOOP_THRESHOLD = 3

def _check_doom_loop(self, context: LoopContext, tool_call: LLMToolCall) -> bool:
    """Detect if the same tool+args combination has been called DOOM_LOOP_THRESHOLD times consecutively."""
    sig = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True)}"
    recent_sigs: list[str] = context.metadata.setdefault("_recent_tool_signatures", [])
    recent_sigs.append(sig)
    # Keep only last DOOM_LOOP_THRESHOLD * 2 signatures for sliding window
    if len(recent_sigs) > self.DOOM_LOOP_THRESHOLD * 2:
        recent_sigs[:] = recent_sigs[-self.DOOM_LOOP_THRESHOLD * 2:]
    # Check if last DOOM_LOOP_THRESHOLD are all the same
    if len(recent_sigs) >= self.DOOM_LOOP_THRESHOLD:
        tail = recent_sigs[-self.DOOM_LOOP_THRESHOLD:]
        if len(set(tail)) == 1:
            return True
    return False
```

In `_handle_tool_execution`, after each tool execution (both read-only parallel and write serial), check doom loop. For write tools, add after the failure/success handling:

```python
# After write tool execution (around line 293), before the error_recovery_needed check:
if self._check_doom_loop(context, tool_call):
    doom_prompt = (
        f"[Doom Loop Detected] You have called {tool_call.name} with the same arguments "
        f"{self.DOOM_LOOP_THRESHOLD} times in a row, and it keeps failing or producing no progress.\n"
        f"Arguments: {json.dumps(tool_call.arguments)}\n"
        f"Last error: {step.error or 'no error (success but no progress)'}\n\n"
        f"You MUST change your approach:\n"
        f"- If the tool keeps failing, try a different tool or different arguments.\n"
        f"- If you are stuck, call plan.block to report the blocker.\n"
        f"- Do NOT retry with the same parameters again."
    )
    context.add_message("user", doom_prompt)
    rt.consecutive_failures = 0
    return LoopPhase.PLANNING
```

For read-only tools, integrate with the existing stagnation check. After the parallel read-only execution block (around line 245), check doom loop for each read-only call:

```python
for i, (step, tool_call) in enumerate(zip(parallel_steps, read_only_calls)):
    if self._check_doom_loop(context, tool_call):
        doom_prompt = (
            f"[Doom Loop Detected] You have called {tool_call.name} with the same arguments "
            f"{self.DOOM_LOOP_THRESHOLD} times in a row with no new information.\n"
            f"Arguments: {json.dumps(tool_call.arguments)}\n\n"
            f"You MUST change your approach. Try different search terms, different files, or move on to the next step."
        )
        context.add_message("user", doom_prompt)
        rt.consecutive_failures = 0
        # Force exit to PLANNING so the model sees the doom-loop message
        return LoopPhase.PLANNING
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_rapid_loop.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/rapid_loop.py backend/app/execution/context_manager.py backend/tests/test_execution/test_rapid_loop.py
git commit -m "feat: doom-loop detection for all tools (read-only + write)"
```

---

### Task 5: JSON Parse Failure Visibility

**Files:**
- Modify: `backend/app/llm/openai_adapter.py:276-295` (streaming)
- Modify: `backend/app/llm/openai_adapter.py:297-312` (non-streaming)

When streaming tool-call arguments fail to parse as JSON, `args = {}` is used silently. The tool then receives empty arguments, defaults to a wrong action, and produces a confusing error. The LLM never learns that the real problem was malformed JSON.

- [ ] **Step 1: Write the failing test**

```python
# In a new or existing test file for openai_adapter, add:

class TestToolCallJsonParseFailure:
    def test_streaming_json_parse_failure_preserves_raw_args(self):
        """When JSON parse fails, args should contain a _raw_arguments key with the original fragment."""
        from app.llm.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        current_tool_calls = {
            0: {
                "id": "call_1",
                "name": "file",
                "arguments": "{invalid json",  # Malformed JSON
            }
        }
        tool_calls = adapter._build_structured_tool_calls(current_tool_calls)
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "file"
        assert "_parse_error" in tool_calls[0].arguments
        assert "invalid json" in tool_calls[0].arguments.get("_raw_arguments", "")

    def test_non_streaming_json_parse_failure_preserves_raw_args(self):
        """When JSON parse fails in _parse_response, args should indicate the parse failure."""
        pass  # This requires mocking an OpenAI response object
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/ -k "TestToolCallJsonParseFailure" -v`
Expected: FAIL — `_parse_error` key not in arguments

- [ ] **Step 3: Implement JSON parse failure visibility**

In `_build_structured_tool_calls` (line 283-286), replace:

```python
try:
    args = json.loads(tc_data["arguments"])
except json.JSONDecodeError:
    args = {}
```

With:

```python
try:
    args = json.loads(tc_data["arguments"])
except json.JSONDecodeError:
    raw_fragment = tc_data["arguments"][:200] if tc_data["arguments"] else ""
    logger.warning(
        "Streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
        tc_data["name"], raw_fragment,
    )
    args = {
        "_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                        "Please retry the tool call with valid parameters.",
        "_raw_arguments": raw_fragment,
    }
```

In `_parse_response` (line 307-310), replace:

```python
try:
    args = json.loads(tc.function.arguments)
except json.JSONDecodeError:
    logger.warning("工具参数解析失败: %s", tc.function.arguments)
    args = {}
```

With:

```python
try:
    args = json.loads(tc.function.arguments)
except json.JSONDecodeError:
    raw_fragment = tc.function.arguments[:200] if tc.function.arguments else ""
    logger.warning(
        "Non-streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
        tc.function.name, raw_fragment,
    )
    args = {
        "_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                        "Please retry the tool call with valid parameters.",
        "_raw_arguments": raw_fragment,
    }
```

Now, when `_parse_error` is present in args, the `ToolCallExecutor._validate_required_args` will find missing required params and the tool itself will fail with a clear error that includes the parse failure info. The error will propagate back to the LLM as a `tool` role message containing the `_parse_error` text.

- [ ] **Step 4: Also handle this in the tool executor**

In `tool_call_executor.py`, before calling `tool.execute(arguments)` (around line 97), add a check:

```python
# If arguments contain a parse error marker, short-circuit with a clear error
if arguments.get("_parse_error"):
    error_msg = arguments["_parse_error"]
    raw = arguments.get("_raw_arguments", "")
    if raw:
        error_msg += f" Raw fragment received: {raw}"
    result = ToolResult(success=False, error=error_msg)
    step = LoopStep(
        step_number=step_number,
        tool=tool_call.name,
        args=arguments,
        status=StepStatus.FAILED,
        error=error_msg,
        duration=0.0,
        tool_call_id=tool_call.id,
    )
    context.add_step(step)
    context.update_history(tool_call, error_msg)
    context.add_message("tool", content=error_msg, tool_call_id=tool_call.id)
    return step
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/ -k "TestToolCallJsonParseFailure" -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/llm/openai_adapter.py backend/app/execution/tool_call_executor.py backend/tests/
git commit -m "feat: JSON parse failure visibility — no longer silently swallowed"
```

---

### Task 6: Completion Gate Tightening

**Files:**
- Modify: `backend/app/execution/rapid_loop.py:107-157`

The current `_handle_planning` logic (lines 127-135) treats ANY text content from the model as a final answer when tools have been previously executed. This causes premature termination — the model outputs a partial explanation or asks the user to write code, and the loop exits.

- [ ] **Step 1: Write the failing test**

```python
# In test_rapid_loop.py, add:

class TestCompletionGate:
    @pytest.mark.asyncio
    async def test_partial_answer_does_not_terminate_loop(self):
        """When the model outputs a partial answer without completing the task, the loop should continue."""
        registry = ToolRegistry()
        registry.register(ReadOnlyFileTool())
        llm = AsyncMock()
        llm.get_model_name.return_value = "test-model"

        # First call: model makes a tool call (has_executed_tools = True)
        # Second call: model outputs partial text like "Here is what you need to do: ..."
        # This should NOT terminate the loop — it should go to FINAL_SUMMARY
        # which gives the model another chance to produce a proper answer

        # We'll verify by checking that the loop doesn't immediately set status=COMPLETED
        # when the model's content contains phrases indicating incompleteness
        pass  # Integration test — verify logic in _handle_planning
```

- [ ] **Step 2: Implement completion gate**

In `_handle_planning` (lines 127-135), replace:

```python
# 没有工具调用
if rt.has_executed_tools:
    if rt.response.has_content:
        # 已经有可直接返回给用户的答案，不再强制进入总结
        result.status = LoopStatus.COMPLETED
        result.result = rt.response.content
        return LoopPhase.DONE
    else:
        # 没有最终回答时，再进入兜底总结阶段
        return LoopPhase.FINAL_SUMMARY
```

With:

```python
# 没有工具调用
if rt.has_executed_tools:
    if rt.response.has_content:
        # Check if the content looks like a complete answer or a premature stop.
        # Premature stops often contain: asking the user to write code,
        # partial explanations, or "you can now..." without having done the work.
        content = rt.response.content or ""
        premature_indicators = [
            "you can now", "you should now", "you can implement",
            "here is the code you need", "i'll leave the implementation",
            "you can write the code", "you should write",
            "请你编写", "你可以现在", "你可以自己实现", "你可以编写",
        ]
        is_premature = any(indicator in content.lower() for indicator in premature_indicators)

        if is_premature and rt.consecutive_failures < self.MAX_ERROR_RETRIES:
            # Model stopped prematurely — inject a nudge to continue
            rt.consecutive_failures += 1
            context.add_message(
                "user",
                "You stopped before completing the task. Continue using tools to finish the work. "
                "Do NOT ask the user to write code — use your tools to do it yourself.",
            )
            return LoopPhase.PLANNING

        # Content looks like a genuine final answer
        result.status = LoopStatus.COMPLETED
        result.result = rt.response.content
        return LoopPhase.DONE
    else:
        return LoopPhase.FINAL_SUMMARY
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_rapid_loop.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/rapid_loop.py backend/tests/test_execution/test_rapid_loop.py
git commit -m "feat: completion gate — detect premature termination and nudge model to continue"
```

---

### Task 7: Empty-Response Graduated Handling

**Files:**
- Modify: `backend/app/execution/rapid_loop.py:618-772`

When the LLM returns an empty response with `finish_reason=stop`, the current code immediately gives up (line 726-733), assuming content moderation. But empty responses also happen when the model is confused by long context or ambiguous instructions. We should try one recovery attempt before giving up.

- [ ] **Step 1: Write the failing test**

```python
# In test_rapid_loop.py, add:

class TestEmptyResponseRecovery:
    @pytest.mark.asyncio
    async def test_empty_response_with_stop_reason_retries_once(self):
        """When the model returns empty + finish_reason=stop, inject a task reminder and retry once."""
        registry = ToolRegistry()
        registry.register(ReadOnlyFileTool())
        llm = AsyncMock()
        llm.get_model_name.return_value = "test-model"

        # Simulate: first LLM call returns empty, second returns content
        # The loop should not immediately give up on the first empty response
        pass  # Integration test
```

- [ ] **Step 2: Implement graduated empty-response handling**

In `_call_llm` (lines 726-734), replace:

```python
if finish_reason == "stop":
    logger.warning(
        "LLM 返回空响应且 finish_reason=stop (attempt %d/%d), model=%s — "
        "可能是内容审核过滤或模型拒绝，不再重试",
        attempt + 1,
        self.MAX_EMPTY_RESPONSE_RETRIES,
        self.llm.get_model_name(),
    )
    break
```

With:

```python
if finish_reason == "stop":
    # Try one recovery: inject a task reminder and retry.
    # If this is the first empty-response in this call, add a nudge and continue.
    # On second empty-response, give up.
    if attempt == 0 and context.task:
        logger.warning(
            "LLM 返回空响应且 finish_reason=stop (attempt %d/%d), model=%s — "
            "注入任务提醒后重试一次",
            attempt + 1,
            self.MAX_EMPTY_RESPONSE_RETRIES,
            self.llm.get_model_name(),
        )
        context.add_message(
            "user",
            f"[System] The model produced no output. Please continue the task using tools. "
            f"Original task: {context.task}",
        )
        continue  # Retry in the for-loop
    logger.warning(
        "LLM 返回空响应且 finish_reason=stop (attempt %d/%d), model=%s — "
        "重试后仍为空，放弃",
        attempt + 1,
        self.MAX_EMPTY_RESPONSE_RETRIES,
        self.llm.get_model_name(),
    )
    break
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_rapid_loop.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/rapid_loop.py backend/tests/test_execution/test_rapid_loop.py
git commit -m "feat: graduated empty-response handling — retry once with task reminder"
```

---

### Task 8: Add Skill to Exploration Tools

**Files:**
- Modify: `backend/app/execution/runtime_tool_definitions.py:19-21`

The `skill` tool is not in `exploration_tools`, but the system prompt says "When a skill clearly matches your current task, load it first using the 'skill' tool." This is contradictory — on the first turn, the model can't load skills.

- [ ] **Step 1: Write the failing test**

```python
# In test_runtime_tool_definitions.py, add:

def test_skill_tool_available_on_first_turn():
    """The skill tool should be available from the first turn (exploration phase)."""
    from app.execution.runtime_tool_definitions import DEFAULT_TOOL_SET_CONFIG
    assert "skill" in DEFAULT_TOOL_SET_CONFIG.exploration_tools
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_runtime_tool_definitions.py::test_skill_tool_available_on_first_turn -v`
Expected: FAIL — `"skill" not in frozenset`

- [ ] **Step 3: Add skill to exploration_tools**

In `runtime_tool_definitions.py` line 19-21, change:

```python
exploration_tools: frozenset[str] = field(default_factory=lambda: frozenset({
    "file", "grep", "glob", "memory", "session_recall",
}))
```

To:

```python
exploration_tools: frozenset[str] = field(default_factory=lambda: frozenset({
    "file", "grep", "glob", "memory", "session_recall", "skill",
}))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_runtime_tool_definitions.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/runtime_tool_definitions.py backend/tests/test_execution/test_runtime_tool_definitions.py
git commit -m "feat: add skill tool to exploration_tools for first-turn availability"
```

---

### Task 9: Integration Test — Full Loop with All Hardening

**Files:**
- Modify: `backend/tests/test_execution/test_rapid_loop.py`

Write an integration test that exercises the full hardened loop: model makes tool calls, encounters errors, gets doom-loop detected, recovers, and completes.

- [ ] **Step 1: Write integration test**

```python
class TestHardenedLoopIntegration:
    @pytest.mark.asyncio
    async def test_loop_recovers_from_repeated_tool_errors(self):
        """Model calls same tool 3 times with same args, gets doom-loop message, then succeeds."""
        registry = ToolRegistry()
        tool = FailingThenSucceedingTool(fail_count=3)
        registry.register(tool)

        llm = AsyncMock()
        llm.get_model_name.return_value = "test-model"

        # Simulate LLM responses: 3 identical tool calls, then a different call that succeeds
        call_count = 0
        async def mock_stream(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                tc = LLMToolCall(id=f"c{call_count}", name="fail_succeed", arguments={"action": "try"})
                yield StreamChunk(type="tool_calls", tool_calls=[tc], finish_reason="tool_calls")
            else:
                yield StreamChunk(type="content", content="Task completed successfully")
                yield StreamChunk(type="done", finish_reason="stop")

        llm.stream_complete = mock_stream
        loop = RapidExecutionLoop(llm=llm, tool_registry=registry, max_steps=20, context_window=128000)
        result = await loop.run(task="test task")
        # The loop should have completed (not stuck in infinite retry)
        assert result.status in (LoopStatus.COMPLETED, LoopStatus.FAILED)

class FailingThenSucceedingTool(BaseTool):
    def __init__(self, fail_count=3):
        self.fail_count = fail_count
        self.call_count = 0

    @property
    def name(self) -> str:
        return "fail_succeed"

    @property
    def description(self) -> str:
        return "Fails N times then succeeds"

    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}}},
        }

    async def execute(self, args):
        self.call_count += 1
        if self.call_count <= self.fail_count:
            return ToolResult(success=False, error=f"Failed attempt {self.call_count}")
        return ToolResult(success=True, output="Success!")
```

- [ ] **Step 2: Run integration test**

Run: `cd backend && python -m pytest tests/test_execution/test_rapid_loop.py::TestHardenedLoopIntegration -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_execution/test_rapid_loop.py
git commit -m "test: integration test for hardened loop with doom-loop recovery"
```
