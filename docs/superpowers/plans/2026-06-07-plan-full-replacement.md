# Plan 全量替换改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Plan 系统从增量操作（create/step_done/block/adjust）改造为全量替换模式，参照 Crush 的 todos 工具设计，同时删除所有 plan 消息注入。

**Architecture:** PlanTool 统一为单一 schema，LLM 每次调用传入完整步骤列表（含状态和 findings），tool 全量替换。删除 loop_message_builder 中的 plan 注入、tool_call_executor 中的 plan 计数、rapid_loop 中的 finalize 逻辑。文件持久化改为 session 级路径。

**Tech Stack:** Python, asyncio, dataclasses, pytest

---

### Task 1: 重写 PlanEngine 数据模型

**Files:**
- Modify: `backend/app/execution/plan_engine.py`
- Test: `backend/tests/test_execution/test_plan_engine.py`

- [ ] **Step 1: Write the failing test for new PlanStep/Plan model**

```python
# backend/tests/test_execution/test_plan_engine.py
from app.execution.plan_engine import Plan, PlanStep


def test_plan_step_has_content_not_id():
    step = PlanStep(content="Fix auth", status="in_progress")
    assert step.content == "Fix auth"
    assert not hasattr(step, "id")
    assert not hasattr(step, "description")


def test_plan_current_step_derived_from_status():
    plan = Plan(
        goal="Fix bug",
        steps=[
            PlanStep(content="Analyze", status="completed", findings="Found bug"),
            PlanStep(content="Fix", status="in_progress"),
            PlanStep(content="Test", status="pending"),
        ],
    )
    assert plan.current_step is not None
    assert plan.current_step.content == "Fix"
    assert not hasattr(plan, "current_step_index")


def test_plan_replace_from():
    plan = Plan(
        goal="Fix bug",
        steps=[
            PlanStep(content="Analyze", status="completed", findings="Found bug"),
            PlanStep(content="Fix", status="in_progress"),
        ],
    )
    new_steps = [
        PlanStep(content="Analyze", status="completed", findings="Found bug"),
        PlanStep(content="Fix", status="completed", findings="Fixed"),
        PlanStep(content="Test", status="in_progress"),
    ]
    changes = plan.replace_from(new_steps)
    assert changes["just_completed"] == ["Fix"]
    assert changes["just_started"] == "Test"
    assert plan.current_step.content == "Test"
    assert plan.steps[0].findings == "Found bug"


def test_plan_replace_from_updates_goal():
    plan = Plan(goal="Old goal", steps=[PlanStep(content="S1", status="pending")])
    plan.replace_from([PlanStep(content="S1", status="pending")], goal="New goal")
    assert plan.goal == "New goal"


def test_plan_is_complete():
    plan = Plan(
        goal="Done",
        steps=[
            PlanStep(content="A", status="completed"),
            PlanStep(content="B", status="completed"),
        ],
    )
    assert plan.is_complete is True


def test_plan_no_in_progress_means_no_current_step():
    plan = Plan(
        goal="Test",
        steps=[
            PlanStep(content="A", status="completed"),
            PlanStep(content="B", status="pending"),
        ],
    )
    assert plan.current_step is None


def test_plan_render_to_markdown_new_format():
    plan = Plan(
        goal="Fix auth",
        steps=[
            PlanStep(content="Analyze", status="completed", findings="Found bug"),
            PlanStep(content="Fix", status="in_progress"),
        ],
    )
    md = plan.render_to_markdown()
    assert "goal: Fix auth" in md
    assert "[completed] Analyze" in md
    assert "[in_progress] Fix" in md
    assert "findings: Found bug" in md


def test_plan_parse_from_markdown_new_format():
    md = """# Execution Plan
goal: Fix auth

## Steps
- [completed] Analyze
  findings: Found bug
- [in_progress] Fix
- [pending] Test
"""
    plan = Plan.parse_from_markdown(md)
    assert plan.goal == "Fix auth"
    assert len(plan.steps) == 3
    assert plan.steps[0].content == "Analyze"
    assert plan.steps[0].status == "completed"
    assert plan.steps[0].findings == "Found bug"
    assert plan.steps[1].content == "Fix"
    assert plan.steps[1].status == "in_progress"
    assert plan.current_step.content == "Fix"


def test_plan_to_dict():
    plan = Plan(
        goal="Test",
        steps=[PlanStep(content="S1", status="pending")],
    )
    d = plan.to_dict()
    assert d["goal"] == "Test"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["content"] == "S1"
    assert "current_step_index" not in d


def test_plan_completed_findings():
    plan = Plan(
        goal="Test",
        steps=[
            PlanStep(content="A", status="completed", findings="Found X"),
            PlanStep(content="B", status="in_progress"),
        ],
    )
    assert plan.completed_findings() == ["Found X"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/test_plan_engine.py -v`
Expected: FAIL — PlanStep no longer has `content` field, `replace_from` not defined

- [ ] **Step 3: Rewrite plan_engine.py**

```python
# backend/app/execution/plan_engine.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PlanStep:
    content: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    findings: str = ""

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "status": self.status,
            "findings": self.findings,
        }


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def current_step(self) -> PlanStep | None:
        for s in self.steps:
            if s.status == "in_progress":
                return s
        return None

    @property
    def is_complete(self) -> bool:
        return bool(self.steps) and all(s.status == "completed" for s in self.steps)

    def replace_from(self, new_steps: list[PlanStep], goal: str | None = None) -> dict:
        old_completed = {s.content for s in self.steps if s.status == "completed"}
        old_in_progress = next(
            (s.content for s in self.steps if s.status == "in_progress"), None
        )
        self.steps = new_steps
        if goal is not None:
            self.goal = goal
        just_completed = [
            s.content for s in new_steps
            if s.status == "completed" and s.content not in old_completed
        ]
        just_started = None
        for s in new_steps:
            if s.status == "in_progress" and s.content != old_in_progress:
                just_started = s.content
                break
        return {
            "just_completed": just_completed,
            "just_started": just_started,
        }

    def completed_findings(self) -> list[str]:
        return [s.findings for s in self.steps if s.status == "completed" and s.findings]

    def render_for_context(self) -> str:
        lines = [f"## 执行计划\n目标: {self.goal}", ""]
        for s in self.steps:
            mark = {
                "pending": "○",
                "in_progress": "►",
                "completed": "✓",
                "blocked": "✗",
            }[s.status]
            lines.append(f"{mark} {s.content}")
            if s.status == "completed" and s.findings:
                lines.append(f"  → {s.findings}")
        return "\n".join(lines)

    def render_to_markdown(self) -> str:
        lines = ["# Execution Plan", f"goal: {self.goal}", "", "## Steps"]
        for s in self.steps:
            lines.append(f"- [{s.status}] {s.content}")
            if s.findings:
                lines.append(f"  findings: {s.findings}")
        return "\n".join(lines)

    @classmethod
    def parse_from_markdown(cls, text: str) -> Plan:
        goal = ""
        steps: list[PlanStep] = []
        for line in text.splitlines():
            line = line.rstrip()
            if line.startswith("goal:"):
                goal = line[len("goal:"):].strip()
                continue
            step_match = re.match(r"^-\s*\[(\w+)\]\s*(.+)$", line)
            if step_match:
                status = step_match.group(1)
                content = step_match.group(2).strip()
                steps.append(PlanStep(content=content, status=status))
                continue
            findings_match = re.match(r"^\s+findings:\s*(.+)$", line)
            if findings_match and steps:
                steps[-1].findings = findings_match.group(1).strip()
        return cls(goal=goal, steps=steps)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/test_plan_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/plan_engine.py backend/tests/test_execution/test_plan_engine.py
git commit -m "refactor: rewrite PlanEngine with full-replacement model"
```

---

### Task 2: 重写 PlanTool

**Files:**
- Modify: `backend/app/tools/plan_tool.py`
- Test: `backend/tests/test_tools/test_plan_tool.py`

- [ ] **Step 1: Write the failing test for new PlanTool**

```python
# backend/tests/test_tools/test_plan_tool.py
import pytest
from app.tools.plan_tool import PlanTool


@pytest.fixture
def tool():
    return PlanTool()


def test_plan_schema_is_flat_and_single_action(tool):
    schema = tool.get_schema()
    params = schema["parameters"]
    assert "action" not in params["properties"]
    assert "steps" in params["properties"]
    assert "goal" in params["properties"]
    assert params["required"] == ["steps"]


def test_plan_schema_steps_items_have_content_status_findings(tool):
    schema = tool.get_schema()
    step_props = schema["parameters"]["properties"]["steps"]["items"]["properties"]
    assert "content" in step_props
    assert "status" in step_props
    assert step_props["status"]["enum"] == ["pending", "in_progress", "completed", "blocked"]
    assert "findings" in step_props


def test_plan_create_on_first_call(tool):
    result = tool.execute({
        "goal": "Fix auth bug",
        "steps": [
            {"content": "Analyze", "status": "in_progress"},
            {"content": "Fix", "status": "pending"},
        ],
    })
    assert result.success
    assert "Plan updated" in result.output
    plan = tool.get_plan()
    assert plan is not None
    assert plan.goal == "Fix auth bug"
    assert len(plan.steps) == 2
    assert plan.current_step.content == "Analyze"


def test_plan_full_replace_on_subsequent_call(tool):
    tool.execute({
        "goal": "Fix auth",
        "steps": [
            {"content": "Analyze", "status": "in_progress"},
            {"content": "Fix", "status": "pending"},
        ],
    })
    result = tool.execute({
        "steps": [
            {"content": "Analyze", "status": "completed", "findings": "Found bug"},
            {"content": "Fix", "status": "in_progress"},
            {"content": "Test", "status": "pending"},
        ],
    })
    assert result.success
    plan = tool.get_plan()
    assert plan.steps[0].status == "completed"
    assert plan.steps[1].status == "in_progress"
    assert len(plan.steps) == 3


def test_plan_rejects_goal_missing_on_first_call(tool):
    result = tool.execute({
        "steps": [{"content": "Do something", "status": "pending"}],
    })
    assert not result.success
    assert "goal" in result.error.lower()


def test_plan_rejects_multiple_in_progress(tool):
    tool.execute({
        "goal": "Test",
        "steps": [{"content": "A", "status": "in_progress"}],
    })
    result = tool.execute({
        "steps": [
            {"content": "A", "status": "in_progress"},
            {"content": "B", "status": "in_progress"},
        ],
    })
    assert not result.success
    assert "in_progress" in result.error.lower()


def test_plan_completed_step_requires_findings(tool):
    tool.execute({
        "goal": "Test",
        "steps": [{"content": "A", "status": "in_progress"}],
    })
    result = tool.execute({
        "steps": [{"content": "A", "status": "completed"}],
    })
    assert not result.success


def test_plan_returns_metadata(tool):
    tool.execute({
        "goal": "Test",
        "steps": [
            {"content": "A", "status": "in_progress"},
            {"content": "B", "status": "pending"},
        ],
    })
    result = tool.execute({
        "steps": [
            {"content": "A", "status": "completed", "findings": "Done"},
            {"content": "B", "status": "in_progress"},
        ],
    })
    assert result.success
    data = result.data
    assert data["is_new"] is False
    assert data["just_completed"] == ["A"]
    assert data["just_started"] == "B"
    assert data["completed"] == 1
    assert data["total"] == 2


def test_plan_no_create_or_progress_schema_methods(tool):
    assert not hasattr(tool, "get_create_schema")
    assert not hasattr(tool, "get_progress_schema")


def test_plan_set_and_get_plan(tool):
    from app.execution.plan_engine import Plan, PlanStep
    plan = Plan(goal="Test", steps=[PlanStep(content="S1", status="pending")])
    tool.set_plan(plan)
    assert tool.get_plan() is plan
    tool.set_plan(None)
    assert tool.get_plan() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_tools/test_plan_tool.py -v`
Expected: FAIL — `get_create_schema` still exists, schema shape mismatch

- [ ] **Step 3: Rewrite plan_tool.py**

```python
# backend/app/tools/plan_tool.py
import logging
from typing import Any

from app.execution.plan_engine import Plan, PlanStep
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PlanTool(BaseTool):

    def __init__(self):
        self._plan: Plan | None = None

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return (
            "Manage execution plans for multi-step tasks. "
            "Send the full step list each call. Keep exactly one step in_progress at a time. "
            "Skip for simple tasks that need fewer than 3 steps."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Overall goal (required on first call, optional after)",
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "What needs to be done (imperative form)",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed", "blocked"],
                                    "description": "Step status",
                                },
                                "findings": {
                                    "type": "string",
                                    "description": "Key results when completed (required when status=completed)",
                                },
                            },
                            "required": ["content", "status"],
                        },
                        "minItems": 1,
                        "maxItems": 12,
                        "description": "The complete step list. Send ALL steps every time, including already completed ones.",
                    },
                },
                "required": ["steps"],
            },
        }

    def set_plan(self, plan: Plan | None):
        self._plan = plan

    def get_plan(self) -> Plan | None:
        return self._plan

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        steps_raw = args.get("steps", [])
        goal = args.get("goal", "")

        steps_result = self._parse_steps(steps_raw)
        if isinstance(steps_result, str):
            return ToolResult(success=False, error=steps_result)
        steps = steps_result

        if not steps:
            return ToolResult(success=False, error="steps 不能为空")

        in_progress_count = sum(1 for s in steps if s.status == "in_progress")
        if in_progress_count > 1:
            return ToolResult(success=False, error="只能有一个步骤处于 in_progress 状态")

        for s in steps:
            if s.status == "completed" and not s.findings:
                return ToolResult(
                    success=False,
                    error=f"已完成步骤需要 findings: {s.content}",
                )

        is_new = self._plan is None
        if is_new:
            if not goal:
                return ToolResult(success=False, error="首次创建计划需要 goal 参数")
            self._plan = Plan(goal=goal, steps=steps)
            changes = {"just_completed": [], "just_started": None}
            if self._plan.current_step:
                changes["just_started"] = self._plan.current_step.content
        else:
            changes = self._plan.replace_from(steps, goal=goal or None)

        plan = self._plan
        current = plan.current_step
        pending = sum(1 for s in plan.steps if s.status == "pending")
        in_prog = sum(1 for s in plan.steps if s.status == "in_progress")
        completed = sum(1 for s in plan.steps if s.status == "completed")
        blocked = sum(1 for s in plan.steps if s.status == "blocked")

        output_parts = [
            f"Plan updated. {pending} pending, {in_prog} in_progress, {completed} completed, {blocked} blocked.",
        ]
        if current:
            output_parts.append(f"[Current] {current.content}")
        output_parts.append("Ensure you use the plan to track your progress. Proceed with the current step.")

        logger.info("Plan updated: %s (%d/%d done)", plan.goal, completed, len(plan.steps))

        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            data={
                "is_new": is_new,
                "just_completed": changes.get("just_completed", []),
                "just_started": changes.get("just_started"),
                "completed": completed,
                "total": len(plan.steps),
                **plan.to_dict(),
            },
        )

    def _parse_steps(self, steps_raw: Any) -> list[PlanStep] | str:
        if not isinstance(steps_raw, list):
            return "steps must be an array"
        steps: list[PlanStep] = []
        for item in steps_raw:
            if not isinstance(item, dict):
                return "Each step must be an object with content and status"
            content = item.get("content", "")
            if not isinstance(content, str) or not content.strip():
                return "Each step requires a non-empty content"
            status = item.get("status", "")
            valid = {"pending", "in_progress", "completed", "blocked"}
            if status not in valid:
                return f"Invalid status '{status}', must be one of {valid}"
            findings = item.get("findings", "")
            if not isinstance(findings, str):
                findings = str(findings)
            steps.append(PlanStep(content=content.strip(), status=status, findings=findings))
        if len(steps) > 12:
            return "steps 最多只能包含 12 个步骤"
        return steps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_tools/test_plan_tool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/plan_tool.py backend/tests/test_tools/test_plan_tool.py
git commit -m "refactor: rewrite PlanTool with full-replacement single-action schema"
```

---

### Task 3: 删除 loop_message_builder.py 中的 plan 消息注入

**Files:**
- Modify: `backend/app/execution/loop_message_builder.py`
- Test: `backend/tests/test_execution/test_loop_message_builder.py`

- [ ] **Step 1: Remove plan injection from build()**

In `loop_message_builder.py`, delete the entire `if context.plan:` block (lines 66-105 after previous P0 edits, the block that adds `plan_parts` as a SYSTEM message). The block starts with `if context.plan:` and ends with the `messages.append(LLMMessage(role=MessageRole.SYSTEM, content="\n\n".join(plan_parts)))`.

- [ ] **Step 2: Remove plan injection from build_final_summary()**

In `loop_message_builder.py`, delete the plan-related block in `build_final_summary()` that injects `context.plan.render_for_context()` as a SYSTEM message.

- [ ] **Step 3: Update tests — remove plan-specific test cases**

In `test_loop_message_builder.py`:
- Delete `test_build_messages_injects_current_plan_step_and_update_requirement` (no longer relevant)
- Delete `test_plan_focus_injected_once_per_step` (focus injection removed)
- Delete `test_per_turn_plan_status_reminder_not_injected_by_message_builder` (no plan injection at all)
- Delete `test_per_turn_plan_status_not_injected_when_no_plan` (trivially true now)
- Delete `test_plan_status_injected_in_plan_context_system_message` (no injection)

- [ ] **Step 4: Run tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/test_loop_message_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/loop_message_builder.py backend/tests/test_execution/test_loop_message_builder.py
git commit -m "refactor: remove all plan message injection from LoopMessageBuilder"
```

---

### Task 4: 清理 tool_call_executor.py 中的 plan 计数逻辑

**Files:**
- Modify: `backend/app/execution/tool_call_executor.py`

- [ ] **Step 1: Remove plan_update_required and steps_since_last_plan_update tracking**

In `tool_call_executor.py`, delete the block at lines 191-202 that:
- Sets `context.metadata["plan_update_required"] = False` and `steps_since_last_plan_update = 0` when PlanTool is executed
- Increments `steps_since_last_plan_update` on non-plan tool calls
- Calls `PlanFileSync().sync()` after plan tool execution

Replace the entire block (from `if isinstance(tool, PlanTool)` through the `elif` that increments the counter) with just:

```python
if isinstance(tool, PlanTool) and tool.get_plan() is not None:
    context.plan = tool.get_plan()
    await self.emit("plan:updated", context.plan.to_dict())
```

Also remove the `from app.execution.plan_file_sync import PlanFileSync` import at the top of the file if it was only used for that sync call.

- [ ] **Step 2: Run tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/ -v -k "tool_call or rapid_loop"`
Expected: Some rapid_loop tests may fail due to old plan model references — will be fixed in Task 5

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/tool_call_executor.py
git commit -m "refactor: remove plan stagnation counter from ToolCallExecutor"
```

---

### Task 5: 清理 rapid_loop.py 中的 plan finalize 逻辑

**Files:**
- Modify: `backend/app/execution/rapid_loop.py`

- [ ] **Step 1: Simplify finally block plan handling**

In `rapid_loop.py`, replace the `if context.plan is not None:` block in the `finally` section (lines 673-692) with:

```python
if context.plan is not None:
    if context.plan_file_path:
        self.plan_file_sync.sync(context.plan, context.plan_file_path, project_path=context.project_path)
    await self._emit("plan:updated", context.plan.to_dict())
```

This removes:
- `was_plan_complete` check
- `finalize_for_completion()` call and plan file deletion
- `finalize_for_failure()` call
- `finalize_for_cancellation()` comment block
- The distinction between COMPLETED/FAILED/CANCELLED — all cases just sync the plan as-is

- [ ] **Step 2: Remove `steps_since_last_plan_update` from RuntimeState initialization**

In `rapid_loop.py`, find `rt.steps_since_last_plan_update = 0` and delete it.

- [ ] **Step 3: Remove plan_file_sync call after plan tool in _confirm_plan_exit**

In `_confirm_plan_exit`, remove the line `self.plan_file_sync.sync(context.plan, context.plan_file_path, project_path=context.project_path)` — the sync will happen in the finally block or via tool internal logic.

- [ ] **Step 4: Fix any remaining references to old Plan model fields**

Search for `current_step.description` or `step.description` references and change to `current_step.content` or `step.content`. Search for `.id` references on plan steps and remove them.

- [ ] **Step 5: Run tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/test_rapid_loop.py -v -x`
Expected: Some failures from old PlanStep field names — fix by updating test code to use `content` instead of `description`

- [ ] **Step 6: Commit**

```bash
git add backend/app/execution/rapid_loop.py
git commit -m "refactor: simplify plan finalization in RapidExecutionLoop"
```

---

### Task 6: 简化 RuntimeToolDefinitions

**Files:**
- Modify: `backend/app/execution/runtime_tool_definitions.py`
- Test: `backend/tests/test_execution/test_runtime_tool_definitions.py`

- [ ] **Step 1: Remove create/progress schema distinction**

In `runtime_tool_definitions.py`:
- Remove the `if isinstance(tool, PlanTool):` branches in `for_plan_mode()`, `for_initial_plan()`, and `for_context()` that choose between `get_create_schema()` and `get_progress_schema()`
- Replace all PlanTool schema selection with simply `tool.get_schema()`
- Remove the `get_plan_tool()` helper if it's only used for schema selection (it may still be needed by bootstrapper — keep if used)

- [ ] **Step 2: Update tests**

In `test_runtime_tool_definitions.py`:
- Remove tests that assert `create` is in/excluded from schema (no more `action` enum)
- Add test that plan tool schema always has `steps` property regardless of plan state
- Update test that checked `step_done` in/out of schema parameters

- [ ] **Step 3: Run tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/test_runtime_tool_definitions.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/runtime_tool_definitions.py backend/tests/test_execution/test_runtime_tool_definitions.py
git commit -m "refactor: unify PlanTool schema in RuntimeToolDefinitions"
```

---

### Task 7: 改造 plan_file_sync 为 session 级路径

**Files:**
- Modify: `backend/app/execution/plan_file_sync.py`
- Test: `backend/tests/test_execution/test_plan_file_sync.py`

- [ ] **Step 1: Update PlanFileSync to use session_id based paths**

In `plan_file_sync.py`:
- Change `write()` to accept `session_id` instead of `slug`, generating path `.reflexion/plans/{session_id}.md`
- Change `sync()` signature to work with session_id or existing path
- Update `render_to_markdown()` / `parse_from_markdown()` is already updated via Task 1's PlanEngine changes
- Update `find_recovery_plan()` to search by session_id pattern

- [ ] **Step 2: Update tests**

In `test_plan_file_sync.py`:
- Update all test to use `session_id` parameter instead of `slug`
- Verify new markdown format round-trips correctly

- [ ] **Step 3: Run tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/test_plan_file_sync.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/plan_file_sync.py backend/tests/test_execution/test_plan_file_sync.py
git commit -m "refactor: switch plan file sync to session-level paths"
```

---

### Task 8: 适配 InitialPlanBootstrapper

**Files:**
- Modify: `backend/app/execution/initial_plan_bootstrapper.py`
- Test: `backend/tests/test_execution/test_initial_plan_bootstrapper.py`

- [ ] **Step 1: Remove `action != "create"` check**

In `initial_plan_bootstrapper.py`:
- Remove `if tool_call.arguments.get("action") != "create": continue` — the new schema has no `action` field
- Remove `context.metadata["plan_update_required"]` and `steps_since_last_plan_update` setting
- Change `plan.current_step.description` to `plan.current_step.content` in `_check_plan_relevance()`
- Update `plan_file_sync.write()` call to use `session_id` instead of `slug`

- [ ] **Step 2: Update tests**

In `test_initial_plan_bootstrapper.py`:
- Update any assertions that check for `action: "create"` in tool call arguments
- Update assertions that reference `description` → `content`

- [ ] **Step 3: Run tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/test_execution/test_initial_plan_bootstrapper.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/initial_plan_bootstrapper.py backend/tests/test_execution/test_initial_plan_bootstrapper.py
git commit -m "refactor: adapt InitialPlanBootstrapper to new plan schema"
```

---

### Task 9: 清理 context_manager.py 中的 plan metadata

**Files:**
- Modify: `backend/app/execution/context_manager.py`

- [ ] **Step 1: Remove plan-specific metadata keys from usage**

In `context_manager.py`:
- No structural changes needed — `metadata` is a generic dict
- The keys `plan_update_required`, `steps_since_last_plan_update`, `_injected_focus_step_id` were set by other files (tool_call_executor, loop_message_builder) which have already been cleaned up in previous tasks
- Just verify no references remain in context_manager.py itself

- [ ] **Step 2: Verify no stale references**

Search the entire backend for `plan_update_required`, `steps_since_last_plan_update`, `_injected_focus_step_id` — all should be gone after Tasks 3-8.

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && rg "plan_update_required|steps_since_last_plan_update|_injected_focus_step_id" backend/`
Expected: No matches

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: verify plan metadata keys fully removed"
```

---

### Task 10: 全量测试与最终验证

**Files:**
- All modified files

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && python -m pytest backend/tests/ -v --tb=short 2>&1 | tail -40`
Expected: All plan-related tests pass. Pre-existing failures in browser/security tests are acceptable.

- [ ] **Step 2: Fix any remaining test failures from PlanStep field rename**

If any tests still reference `PlanStep(id=...)`, `step.description`, or `step.id`, fix them to use `PlanStep(content=...)` and `step.content`.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: fix remaining test references to old PlanStep fields"
```
