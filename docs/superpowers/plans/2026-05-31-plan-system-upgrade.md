# Plan System Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the plan system from "soft prompt-only" to "prompt-strengthened + stagnation detection + plan-file persistence + plan_exit agent-switching", solving the core problem that LLMs forget to call `plan.step_done`.

**Architecture:** Three-layer improvement: (1) Stagnation detection with 3-level escalating reminders in the main loop, (2) plan file persistence at `.reflexion/plans/` for crash recovery, (3) `plan_exit` tool for physical plan→build agent transition with execution-instruction injection. The Plan/PlanStep data model remains the source of truth; the plan file is its persistent mirror.

**Tech Stack:** Python 3.12+, asyncio, dataclasses, Pydantic

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/app/execution/plan_engine.py` | Plan/PlanStep data model + `render_to_markdown()` + `parse_from_markdown()` |
| `backend/app/execution/plan_file_sync.py` | **NEW** — Plan↔file bidirectional sync, lifecycle (create/sync/delete/recover) |
| `backend/app/tools/plan_exit_tool.py` | **NEW** — plan_exit tool definition |
| `backend/app/execution/models.py` | RuntimeState: add `steps_since_last_plan_update` |
| `backend/app/execution/loop_message_builder.py` | 3-level stagnation reminders in plan context injection |
| `backend/app/execution/prompt_manager.py` | Strengthen build prompt + plan_mode 5-phase prompt |
| `backend/app/execution/tool_call_executor.py` | Stagnation counter update + plan_exit handling |
| `backend/app/execution/rapid_loop.py` | Agent-mode dynamic switch + stagnation guard logic + plan_exit event handling |
| `backend/app/execution/context_manager.py` | Add `plan_file_path` field |
| `backend/app/execution/initial_plan_bootstrapper.py` | Check recovery point on startup |
| `backend/app/execution/runtime_tool_definitions.py` | Expose plan_exit for plan agent |
| `backend/app/api/routes/websocket.py` | Add `plan:exit_confirmed`, `plan:clear` message types |
| `backend/app/services/agent_service.py` | Handle plan_exit event forwarding |
| `backend/tests/test_execution/test_plan_engine.py` | **NEW** — tests for markdown round-trip |
| `backend/tests/test_execution/test_plan_file_sync.py` | **NEW** — tests for file sync |
| `backend/tests/test_execution/test_loop_message_builder.py` | Update existing tests for 3-level reminders |
| `backend/tests/test_execution/test_runtime_tool_definitions.py` | Update for plan_exit exposure |

---

### Task 1: Plan Engine — Markdown Round-Trip

**Files:**
- Modify: `backend/app/execution/plan_engine.py`
- Create: `backend/tests/test_execution/test_plan_engine.py`

- [ ] **Step 1: Write the failing test for `render_to_markdown`**

```python
# backend/tests/test_execution/test_plan_engine.py
import pytest
from app.execution.plan_engine import Plan, PlanStep


def test_render_to_markdown_full_plan():
    plan = Plan(
        goal="Implement X feature",
        steps=[
            PlanStep(id=1, description="Analyze plan_tool.py", status="completed", findings="plan_update_required is a toggle"),
            PlanStep(id=2, description="Modify plan_engine.py", status="in_progress"),
            PlanStep(id=3, description="Add step type detection", status="pending"),
            PlanStep(id=4, description="Test the changes", status="blocked", findings="Missing test fixture"),
        ],
        current_step_index=1,
    )
    md = plan.render_to_markdown()
    assert "goal: Implement X feature" in md
    assert "[completed] Analyze plan_tool.py" in md
    assert "[in_progress] Modify plan_engine.py" in md
    assert "[pending] Add step type detection" in md
    assert "[blocked] Test the changes" in md
    assert "findings: plan_update_required is a toggle" in md
    assert "findings: Missing test fixture" in md


def test_parse_from_markdown_round_trip():
    plan = Plan(
        goal="Implement X feature",
        steps=[
            PlanStep(id=1, description="Analyze plan_tool.py", status="completed", findings="found toggle"),
            PlanStep(id=2, description="Modify plan_engine.py", status="in_progress"),
            PlanStep(id=3, description="Test changes", status="pending"),
        ],
        current_step_index=1,
    )
    md = plan.render_to_markdown()
    restored = Plan.parse_from_markdown(md)
    assert restored.goal == plan.goal
    assert len(restored.steps) == len(plan.steps)
    assert restored.steps[0].status == "completed"
    assert restored.steps[0].findings == "found toggle"
    assert restored.steps[1].status == "in_progress"
    assert restored.steps[2].status == "pending"
    assert restored.current_step_index == 1


def test_parse_from_markdown_empty_findings():
    md = """# 执行计划
goal: Simple task

## 步骤
1. [in_progress] Do something
"""
    plan = Plan.parse_from_markdown(md)
    assert plan.goal == "Simple task"
    assert len(plan.steps) == 1
    assert plan.steps[0].status == "in_progress"
    assert plan.steps[0].findings == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_plan_engine.py -v`
Expected: FAIL — `parse_from_markdown` does not exist, `render_to_markdown` does not exist

- [ ] **Step 3: Implement `render_to_markdown` and `parse_from_markdown`**

Add these methods to `Plan` class in `backend/app/execution/plan_engine.py`:

```python
def render_to_markdown(self) -> str:
    lines = [f"# 执行计划", f"goal: {self.goal}", ""]
    lines.append("## 步骤")
    for s in self.steps:
        findings_part = f"  findings: {s.findings}" if s.findings else ""
        lines.append(f"{s.id}. [{s.status}] {s.description}")
        if findings_part:
            lines.append(findings_part)
    return "\n".join(lines)

@classmethod
def parse_from_markdown(cls, text: str) -> "Plan":
    import re
    goal = ""
    steps: list[PlanStep] = []
    current_step_index = -1

    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("goal:"):
            goal = line[len("goal:"):].strip()
            continue

        step_match = re.match(r"^(\d+)\.\s*\[(\w+)\]\s*(.+)$", line)
        if step_match:
            step_id = int(step_match.group(1))
            status = step_match.group(2)
            description = step_match.group(3).strip()
            steps.append(PlanStep(id=step_id, description=description, status=status))
            if status == "in_progress":
                current_step_index = len(steps) - 1
            continue

        findings_match = re.match(r"^\s+findings:\s*(.+)$", line)
        if findings_match and steps:
            steps[-1].findings = findings_match.group(1).strip()

    return cls(goal=goal, steps=steps, current_step_index=current_step_index)
```

Also fix `PlanStep.to_dict()` to include `findings`:

```python
def to_dict(self) -> dict:
    return {
        "id": self.id,
        "description": self.description,
        "status": self.status,
        "findings": self.findings,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_plan_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/plan_engine.py backend/tests/test_execution/test_plan_engine.py
git commit -m "feat: add markdown round-trip to Plan engine for file persistence"
```

---

### Task 2: Plan File Sync

**Files:**
- Create: `backend/app/execution/plan_file_sync.py`
- Create: `backend/tests/test_execution/test_plan_file_sync.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_execution/test_plan_file_sync.py
import os
import tempfile
import pytest
from app.execution.plan_engine import Plan, PlanStep
from app.execution.plan_file_sync import PlanFileSync


def test_write_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Test goal",
            steps=[PlanStep(id=1, description="Step 1", status="in_progress")],
            current_step_index=0,
        )
        path = sync.write(plan, slug="test-goal")
        assert os.path.exists(path)
        content = open(path).read()
        assert "goal: Test goal" in content


def test_read_recovers_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(
            goal="Test goal",
            steps=[
                PlanStep(id=1, description="Step 1", status="completed", findings="done"),
                PlanStep(id=2, description="Step 2", status="in_progress"),
            ],
            current_step_index=1,
        )
        path = sync.write(plan, slug="test-goal")
        recovered = sync.read(path)
        assert recovered is not None
        assert recovered.goal == "Test goal"
        assert len(recovered.steps) == 2
        assert recovered.steps[0].status == "completed"


def test_delete_removes_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Test", steps=[PlanStep(id=1, description="S1", status="in_progress")], current_step_index=0)
        path = sync.write(plan, slug="test")
        assert os.path.exists(path)
        sync.delete(path)
        assert not os.path.exists(path)


def test_find_recovery_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        plan = Plan(goal="Recover me", steps=[PlanStep(id=1, description="S1", status="in_progress")], current_step_index=0)
        sync.write(plan, slug="recover-test")
        found = sync.find_recovery_plan()
        assert found is not None
        assert "recover-test" in found


def test_find_recovery_plan_no_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = PlanFileSync(base_dir=tmpdir)
        assert sync.find_recovery_plan() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_plan_file_sync.py -v`
Expected: FAIL — module `plan_file_sync` does not exist

- [ ] **Step 3: Implement `PlanFileSync`**

```python
# backend/app/execution/plan_file_sync.py
import logging
import os
from datetime import datetime

from app.execution.plan_engine import Plan

logger = logging.getLogger(__name__)


class PlanFileSync:
    """Bidirectional sync between Plan objects and .reflexion/plans/ markdown files."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir

    def _resolve_base_dir(self, project_path: str | None = None) -> str:
        if self.base_dir:
            return self.base_dir
        root = project_path or os.getcwd()
        return os.path.join(root, ".reflexion", "plans")

    def _make_filename(self, slug: str) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_slug = slug.replace(" ", "-").lower()[:40]
        return f"{date_str}-{safe_slug}.md"

    def write(self, plan: Plan, slug: str = "task", project_path: str | None = None) -> str:
        base = self._resolve_base_dir(project_path)
        os.makedirs(base, exist_ok=True)
        filename = self._make_filename(slug)
        path = os.path.join(base, filename)
        content = plan.render_to_markdown()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("计划文件已写入: %s", path)
        return path

    def sync(self, plan: Plan, path: str) -> None:
        content = plan.render_to_markdown()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug("计划文件已同步: %s", path)

    def read(self, path: str) -> Plan | None:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return Plan.parse_from_markdown(content)

    def delete(self, path: str) -> None:
        if os.path.exists(path):
            os.remove(path)
            logger.info("计划文件已删除: %s", path)

    def find_recovery_plan(self, project_path: str | None = None) -> str | None:
        base = self._resolve_base_dir(project_path)
        if not os.path.isdir(base):
            return None
        md_files = sorted(
            [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".md")],
            key=lambda p: os.path.getmtime(p),
            reverse=True,
        )
        for path in md_files:
            plan = self.read(path)
            if plan and not plan.is_complete:
                return path
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution/test_plan_file_sync.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/plan_file_sync.py backend/tests/test_execution/test_plan_file_sync.py
git commit -m "feat: add PlanFileSync for plan file persistence and recovery"
```

---

### Task 3: RuntimeState — Stagnation Counter

**Files:**
- Modify: `backend/app/execution/models.py`

- [ ] **Step 1: Add `steps_since_last_plan_update` to RuntimeState**

In `backend/app/execution/models.py`, add the field to the `RuntimeState` dataclass:

```python
@dataclass
class RuntimeState:
    """单次 run 的可变状态快照 — handler 只操作这个对象"""

    phase: LoopPhase = LoopPhase.PLANNING
    step_num: int = 0
    turn_retries: int = 0
    consecutive_failures: int = 0
    has_executed_tools: bool = False
    response: LLMResponse | None = None
    approval_resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_result: dict | None = None
    read_only_passes_used: int = 0
    stagnant_read_only_passes: int = 0
    steps_since_last_plan_update: int = 0
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: PASS — new field has default value, no behavioral change

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/models.py
git commit -m "feat: add steps_since_last_plan_update to RuntimeState for stagnation detection"
```

---

### Task 4: Context Manager — Plan File Path

**Files:**
- Modify: `backend/app/execution/context_manager.py`

- [ ] **Step 1: Add `plan_file_path` to LoopContext**

In `backend/app/execution/context_manager.py`, add the field:

```python
def __init__(self, task: str, project_path: str | None = None, run_id: str | None = None, agent_mode: str = "build"):
    self.task = task
    self.project_path = project_path
    self.run_id = run_id or f"run-{id(self)}"
    self.agent_mode = agent_mode
    self.history: list[dict[str, Any]] = []
    self.steps: list[LoopStep] = []
    self.messages: list[dict[str, Any]] = []
    self.current_step_number = 0
    self.workspace_snapshot: dict[str, Any] = {}
    self.system_sections: list[str] = []
    self.supplemental_context: str | None = None
    self.plan: Plan | None = None
    self.plan_file_path: str | None = None
    self.total_tokens: int = 0
    self.compacted_summary: str | None = None
    self.group_count: int = 0
    self.metadata: dict[str, Any] = {}
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `cd backend && python -m pytest tests/test_execution/test_context_manager.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/context_manager.py
git commit -m "feat: add plan_file_path to LoopContext"
```

---

### Task 5: 3-Level Stagnation Reminders in Loop Message Builder

**Files:**
- Modify: `backend/app/execution/loop_message_builder.py`
- Modify: `backend/tests/test_execution/test_loop_message_builder.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_execution/test_loop_message_builder.py`:

```python
def test_plan_stagnation_warning_level_1():
    context = LoopContext(task="test", project_path="/tmp")
    context.plan = Plan(
        goal="Test goal",
        steps=[PlanStep(id=1, description="Step 1", status="in_progress")],
        current_step_index=0,
    )
    context.metadata["plan_update_required"] = True
    context.metadata["steps_since_last_plan_update"] = 5
    builder = _make_builder()
    messages = builder.build(context)
    plan_msg = _find_plan_message(messages)
    assert plan_msg is not None
    assert "⚠️" in plan_msg.content or "Plan reminder" in plan_msg.content
    assert "5 轮" in plan_msg.content or "5 tool calls" in plan_msg.content


def test_plan_stagnation_warning_level_2():
    context = LoopContext(task="test", project_path="/tmp")
    context.plan = Plan(
        goal="Test goal",
        steps=[PlanStep(id=1, description="Step 1", status="in_progress")],
        current_step_index=0,
    )
    context.metadata["plan_update_required"] = True
    context.metadata["steps_since_last_plan_update"] = 10
    builder = _make_builder()
    messages = builder.build(context)
    plan_msg = _find_plan_message(messages)
    assert plan_msg is not None
    assert "🚨" in plan_msg.content or "WARNING" in plan_msg.content


def test_plan_stagnation_warning_level_3():
    context = LoopContext(task="test", project_path="/tmp")
    context.plan = Plan(
        goal="Test goal",
        steps=[PlanStep(id=1, description="Step 1", status="in_progress")],
        current_step_index=0,
    )
    context.metadata["plan_update_required"] = True
    context.metadata["steps_since_last_plan_update"] = 15
    builder = _make_builder()
    messages = builder.build(context)
    plan_msg = _find_plan_message(messages)
    assert plan_msg is not None
    assert "CRITICAL" in plan_msg.content


def _find_plan_message(messages):
    for msg in messages:
        if msg.role == MessageRole.SYSTEM and "执行计划" in (msg.content or ""):
            return msg
    return None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution/test_loop_message_builder.py -v -k stagnation`
Expected: FAIL — current code has no stagnation levels

- [ ] **Step 3: Implement 3-level stagnation reminders**

Replace the plan context injection block in `backend/app/execution/loop_message_builder.py` `build()` method (lines 65-92) with:

```python
        if context.plan:
            plan_parts = [context.plan.render_for_context()]
            current_step = context.plan.current_step
            if current_step is not None:
                completed = sum(1 for s in context.plan.steps if s.status == "completed")
                total = len(context.plan.steps)
                plan_parts.append(
                    f"### Current focus (step {current_step.id}/{total}, {completed} completed):\n"
                    f"Goal: {context.plan.goal}\n"
                    f"Task: {current_step.description}\n"
                    "You MUST focus on completing this step. "
                    "When done, immediately call plan.step_done with findings. "
                    "If blocked, call plan.block with the reason."
                )
            if context.metadata.get("plan_update_required"):
                stagnant = context.metadata.get("steps_since_last_plan_update", 0)
                if stagnant >= 15:
                    plan_parts.append(
                        "🔴 CRITICAL: 当前步骤已执行 15+ 轮工具调用但未更新计划状态。"
                        "必须立即调用 plan.step_done 或 plan.block。"
                        "忽略计划更新会导致执行效率严重下降。"
                    )
                elif stagnant >= 10:
                    plan_parts.append(
                        "🚨 Plan WARNING: 当前步骤已执行 10+ 轮工具调用但未更新计划状态。"
                        "请立即评估当前步骤是否已完成，如果是，调用 plan.step_done。"
                    )
                elif stagnant >= 5:
                    plan_parts.append(
                        "⚠️ Plan reminder: 当前步骤已执行 5 轮工具调用但未更新计划状态。"
                        "一个步骤可以需要多次工具调用，但如果步骤已完成，请调用 plan.step_done。"
                    )
                else:
                    plan_parts.append(
                        "Plan update reminder: a single plan step may require multiple tool calls. "
                        "Continue using tools while the current step is still in progress. "
                        "When the current step is complete, blocked, or needs replanning, "
                        "call plan.step_done, plan.block, or plan.adjust."
                    )
            completed_findings = context.plan.completed_findings()
            if completed_findings:
                findings_text = "\n".join(f"- {f}" for f in completed_findings)
                plan_parts.append(f"Findings from completed steps:\n{findings_text}")
            messages.append(
                LLMMessage(role=MessageRole.SYSTEM, content="\n\n".join(plan_parts))
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_execution/test_loop_message_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/loop_message_builder.py backend/tests/test_execution/test_loop_message_builder.py
git commit -m "feat: add 3-level stagnation reminders for plan step tracking"
```

---

### Task 6: Prompt Manager — Strengthen Build Prompt + Plan Mode 5-Phase

**Files:**
- Modify: `backend/app/execution/prompt_manager.py`

- [ ] **Step 1: Strengthen the build prompt's Execution plan section**

In the `system` template (lines 92-98), replace the existing `## Execution plan:` section with:

```python
            template="""You are an autonomous coding agent.
You help users with coding tasks by using tools.

## Skill-first rule:
When a skill clearly matches your current task, load it first using the 'skill' tool.
Skills contain proven workflows for complex tasks — following them leads to better outcomes.
If a skill matches, load and follow it. Skill hard gates are important safeguards.

## Environment:
- Working directory: $working_directory
- Platform: $platform
- Today's date: $date
- Is directory a git repo: $is_git_repo

## How to use tools:
You have access to the following tools.
When you need to use a tool, simply call it.
The system will handle the execution.

## Core discipline:
- Observe → Plan → Act. Never edit a file you have not read first.
- Keep changes minimal and scoped to the user's request.
  Do not refactor or modify unrelated code unless the user asks for it.
- Before editing a file, read the relevant section first unless the change is trivial.
- Prefer the edit tool with action=str_replace over patch or write.
  str_replace supports fuzzy matching (indentation, whitespace differences are tolerated).
- Use write ONLY when creating a brand-new file.
  NEVER use write to overwrite an existing file.
- Use patch only for complex multi-hunk changes where diff format is more appropriate.

## Tool and shell rules:
- Read only the minimum relevant file sections needed.
- Prefer targeted search (grep, glob) before large file reads.
- Avoid reading entire repositories or very large files when a specific section suffices.
- Shell commands are executed via argv, NOT through a shell.
- NEVER use pipe `|`, redirect `>` `>>` `2>` `/dev/null`,
  chain `&&` `||` `;`, or command substitution `` ` `` `$()`.
- Use a single simple command per call.
- NEVER run destructive commands (rm -rf, git reset --hard, sudo, git clean -fd)
  unless explicitly requested by the user.
- Do not use network-related commands unless required by the task.

## Stopping rules:
- Stop when the user's request is fully satisfied.
- Do not continue exploring once the required change is completed.
- Avoid repeated tool calls that do not produce new information.
- After 2 failed attempts on the same action, explain the issue and ask the user instead of retrying indefinitely.
- Never restart investigation from scratch unless a concrete prior finding was disproven.
- At most one broad exploration pass and one targeted follow-up pass per task.
- If the last tool batch produced no new facts, stop exploring and answer or ask for clarification.
- Before any re-check, state which exact prior claim is being verified.

## Error handling:
- If a tool call fails, first diagnose WHY it failed before retrying.
- Do not make speculative large changes without evidence.
- Do not blindly retry with the same parameters.

## Communication:
- Answer the user's actual question directly once you have enough information.
- Keep any explanation of your process brief and natural unless the user explicitly asks for details.
- When done, provide a helpful final answer, not a rigid operation log.

## Execution plan:
- Initial plan creation is handled before normal execution starts.
- If an execution plan is present, you MUST track progress by calling plan.step_done VERY frequently.
- It is CRITICAL that you mark steps as completed as soon as the work for that step is done.
- Do NOT wait until all steps are finished to update the plan — update after EACH step.
- When a step is fully done, call plan.step_done IMMEDIATELY before starting the next step.
- When a step is blocked, call plan.block with the reason.
- Do not create a second plan during normal execution.""",
```

- [ ] **Step 2: Replace plan_mode template with 5-phase workflow**

Replace the `plan_mode` template (lines 102-134) with:

```python
        self.register_template(
            name="plan_mode",
            template="""You are a planning agent. You analyze code and create execution plans, but you NEVER modify any project source files or run shell commands.

## Environment:
- Working directory: $working_directory
- Platform: $platform
- Today's date: $date
- Is directory a git repo: $is_git_repo

## 5-Phase Planning Workflow:

### Phase 1: Initial Understanding
Search and read code to understand the current state. Use grep, glob, and file tools.
Ask the user questions if the request is ambiguous.

### Phase 2: Design
Analyze the best approach. Consider alternatives and trade-offs.

### Phase 3: Review
Verify your understanding aligns with the user's intent.
Re-read critical files if needed.

### Phase 4: Create Plan
Call plan.create to create a structured execution plan with high-level steps.
Each step should be concise and actionable.

### Phase 5: Exit Planning
Call plan_exit to indicate planning is complete and request switching to execution mode.

## Rules:
- You can ONLY read files, search code, and call plan tools.
- Do NOT edit any project source files.
- Do NOT run shell commands.
- Create the plan using plan.create (NOT by writing a plan file).
- When your plan is ready, call plan_exit to switch to execution mode.""",
            variables=["working_directory", "platform", "date", "is_git_repo"],
        )
```

- [ ] **Step 3: Run tests to verify no breakage**

Run: `cd backend && python -m pytest tests/test_execution/test_prompt_manager.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/prompt_manager.py
git commit -m "feat: strengthen build prompt plan rules + plan mode 5-phase workflow"
```

---

### Task 7: Plan Exit Tool

**Files:**
- Create: `backend/app/tools/plan_exit_tool.py`

- [ ] **Step 1: Implement the plan_exit tool**

```python
# backend/app/tools/plan_exit_tool.py
import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PlanExitTool(BaseTool):
    """Request switching from plan agent to build agent after planning is complete."""

    @property
    def name(self) -> str:
        return "plan_exit"

    @property
    def description(self) -> str:
        return (
            "Request switching to execution mode after planning is complete. "
            "Call this when you have created a plan and are ready for the build agent to execute it. "
            "Do NOT call this before creating a plan with plan.create. "
            "Do NOT call this if you still have questions about the implementation."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of the plan for the build agent",
                    },
                },
                "required": [],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        summary = args.get("summary", "")
        logger.info("plan_exit called: %s", summary[:100] if summary else "(no summary)")
        return ToolResult(
            success=True,
            output="Plan exit requested. Waiting for user confirmation to switch to build mode.",
            data={"plan_exit_requested": True, "summary": summary},
        )
```

- [ ] **Step 2: Register the tool in the tool registry**

Find where tools are registered (likely in `agent_service.py` `_build_run_tool_registry`). Add:

```python
from app.tools.plan_exit_tool import PlanExitTool
# ... in _build_run_tool_registry:
registry.register(PlanExitTool())
```

Check `agent_service.py` for `_build_run_tool_registry` method and add the registration there.

- [ ] **Step 3: Run existing tests**

Run: `cd backend && python -m pytest tests/ -v -k "not slow" --timeout=30`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/tools/plan_exit_tool.py
git commit -m "feat: add PlanExitTool for plan→build agent transition"
```

---

### Task 8: Tool Call Executor — Stagnation Counter + Plan Exit Handling

**Files:**
- Modify: `backend/app/execution/tool_call_executor.py`

- [ ] **Step 1: Update stagnation counter in execute method**

In `backend/app/execution/tool_call_executor.py`, after the existing plan sync block (lines 169-174), update the stagnation tracking:

Replace lines 169-174:
```python
            if isinstance(tool, PlanTool) and tool.get_plan() is not None:
                context.plan = tool.get_plan()
                context.metadata["plan_update_required"] = False
                await self.emit("plan:updated", context.plan.to_dict())
            elif context.plan is not None and tool_call.name != "plan":
                context.metadata["plan_update_required"] = True
```

With:
```python
            if isinstance(tool, PlanTool) and tool.get_plan() is not None:
                context.plan = tool.get_plan()
                context.metadata["plan_update_required"] = False
                context.metadata["steps_since_last_plan_update"] = 0
                await self.emit("plan:updated", context.plan.to_dict())
            elif context.plan is not None and tool_call.name != "plan":
                context.metadata["plan_update_required"] = True
                prev = context.metadata.get("steps_since_last_plan_update", 0)
                context.metadata["steps_since_last_plan_update"] = prev + 1
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/tool_call_executor.py
git commit -m "feat: update stagnation counter on plan vs non-plan tool execution"
```

---

### Task 9: Runtime Tool Definitions — Expose plan_exit for Plan Agent

**Files:**
- Modify: `backend/app/execution/runtime_tool_definitions.py`
- Modify: `backend/tests/test_execution/test_runtime_tool_definitions.py`

- [ ] **Step 1: Update `for_plan_mode` to include plan_exit and plan tools**

In `backend/app/execution/runtime_tool_definitions.py`, modify `for_plan_mode()`:

```python
    def for_plan_mode(self) -> list[LLMToolDefinition]:
        from app.tools.plan_exit_tool import PlanExitTool
        from app.tools.plan_tool import PlanTool

        definitions: list[LLMToolDefinition] = []
        for name in self._ordered_tool_names():
            if name not in self.config.plan_mode_tools:
                continue
            tool = self.tool_registry.get(name)
            if tool is None:
                continue
            if isinstance(tool, PlanTool):
                definitions.append(
                    self.tool_registry.definition_from_schema(tool.get_create_schema())
                )
                continue
            definitions.append(self.tool_registry.definition_from_schema(tool.get_schema()))

        plan_exit = self.tool_registry.get("plan_exit")
        if isinstance(plan_exit, PlanExitTool):
            definitions.append(
                self.tool_registry.definition_from_schema(plan_exit.get_schema())
            )

        return definitions
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_execution/test_runtime_tool_definitions.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/runtime_tool_definitions.py
git commit -m "feat: expose plan_exit + plan.create for plan agent mode"
```

---

### Task 10: Rapid Loop — Agent-Mode Switch + Plan Exit Event + Plan File Sync

**Files:**
- Modify: `backend/app/execution/rapid_loop.py`
- Modify: `backend/app/execution/initial_plan_bootstrapper.py`

This is the largest task. It integrates all the pieces.

- [ ] **Step 1: Add PlanFileSync to RapidExecutionLoop**

In `backend/app/execution/rapid_loop.py`, add import and initialization:

```python
from app.execution.plan_file_sync import PlanFileSync
```

In `__init__`, add:
```python
        self.plan_file_sync = PlanFileSync()
```

- [ ] **Step 2: Update bootstrap to check for recovery plans**

In `backend/app/execution/initial_plan_bootstrapper.py`, add recovery logic at the start of `bootstrap()`:

```python
    async def bootstrap(self, context: LoopContext) -> None:
        from app.execution.plan_file_sync import PlanFileSync

        plan_tool = self.tool_definitions.get_plan_tool()
        if plan_tool is None:
            return

        plan_tool.set_plan(None)

        # Check for recovery plan file
        plan_file_sync = PlanFileSync()
        recovery_path = plan_file_sync.find_recovery_plan(context.project_path)
        if recovery_path is not None:
            recovered_plan = plan_file_sync.read(recovery_path)
            if recovered_plan is not None:
                context.plan = recovered_plan
                context.plan_file_path = recovery_path
                context.metadata["plan_update_required"] = False
                context.metadata["steps_since_last_plan_update"] = 0
                await self.emit("plan:updated", context.plan.to_dict())
                await self.emit("plan:recovered", {"path": recovery_path, "goal": recovered_plan.goal})
                return

        if context.plan is not None:
            return

        tool_calls: list[LLMToolCall] = []
        tools = self.tool_definitions.for_initial_plan()
        messages = self.message_builder.build_initial_plan(context)

        async for chunk in self.llm.stream_complete(messages, tools):
            if chunk.type == "tool_calls":
                tool_calls = chunk.tool_calls
                break
            if chunk.type == "done":
                break
            if chunk.type == "error":
                raise RuntimeError(chunk.error or "LLM 初始计划判断失败")

        for tool_call in tool_calls:
            if tool_call.name != plan_tool.name:
                continue
            if tool_call.arguments.get("action") != "create":
                continue

            result = await plan_tool.execute(tool_call.arguments)
            if result.success and plan_tool.get_plan() is not None:
                context.plan = plan_tool.get_plan()
                context.metadata["plan_update_required"] = False
                context.metadata["steps_since_last_plan_update"] = 0
                # Write plan file for persistence
                slug = context.task[:40].replace(" ", "-").lower()
                plan_path = plan_file_sync.write(context.plan, slug=slug, project_path=context.project_path)
                context.plan_file_path = plan_path
                await self.emit("plan:updated", context.plan.to_dict())
            elif result.error:
                context.add_message("system", f"初始计划创建失败: {result.error}")
            return
```

- [ ] **Step 3: Handle plan_exit in _handle_tool_execution**

In `backend/app/execution/rapid_loop.py`, in `_handle_tool_execution`, add plan_exit handling before the existing read-only/write tool split. Add after the `write_calls = []` line and before read-only execution:

```python
        # Handle plan_exit — emit event, wait for user confirmation
        for tool_call in list(rt.response.tool_calls):
            if tool_call.name == "plan_exit":
                rt.step_num += 1
                step = await self.tool_executor.execute(tool_call, context, rt.step_num)
                result.steps.append(step)
                context.add_step(step)
                if step.status == StepStatus.SUCCESS:
                    await self._emit("plan:exit_requested", {
                        "run_id": result.id,
                        "summary": step.args.get("summary", ""),
                    })
                    # Store exit request in context for WebSocket to handle
                    context.metadata["plan_exit_requested"] = True
                    context.metadata["plan_exit_summary"] = step.args.get("summary", "")
                return LoopPhase.PLANNING
```

- [ ] **Step 4: Handle plan_exit confirmation (agent mode switch)**

Add a method to `RapidExecutionLoop`:

```python
    async def confirm_plan_exit(self, context: LoopContext, rt: RuntimeState) -> None:
        """Handle user confirmation of plan_exit — switch to build mode."""
        context.agent_mode = "build"
        rt.steps_since_last_plan_update = 0
        context.metadata["plan_exit_requested"] = False
        summary = context.metadata.pop("plan_exit_summary", "")
        injection = f"计划已批准，开始执行。{summary}"
        if context.plan_file_path:
            injection += f"\n计划文件: {context.plan_file_path}"
        context.add_message("user", injection)
        # Sync plan file
        if context.plan and context.plan_file_path:
            self.plan_file_sync.sync(context.plan, context.plan_file_path)
```

- [ ] **Step 5: Sync plan file after plan tool execution**

In the `_handle_tool_execution` method, after all tool calls are processed (before the final `return LoopPhase.PLANNING`), add plan file sync:

```python
        # Sync plan file after plan tool changes
        if context.plan and context.plan_file_path:
            self.plan_file_sync.sync(context.plan, context.plan_file_path)
```

- [ ] **Step 6: Delete plan file on completion**

In the `finally` block of `run()` (around line 526), add after plan finalization:

```python
                if context.plan is not None:
                    if loop_result.status == LoopStatus.COMPLETED:
                        context.plan.finalize_for_completion()
                        # Delete plan file on successful completion
                        if context.plan_file_path:
                            self.plan_file_sync.delete(context.plan_file_path)
                            await self._emit("plan:file_deleted", {"path": context.plan_file_path})
                    elif loop_result.status == LoopStatus.FAILED:
                        context.plan.finalize_for_failure()
                    elif loop_result.status == LoopStatus.CANCELLED:
                        context.plan.finalize_for_cancellation()
                    await self._emit("plan:updated", context.plan.to_dict())
```

- [ ] **Step 7: Run tests**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/execution/rapid_loop.py backend/app/execution/initial_plan_bootstrapper.py
git commit -m "feat: integrate plan file sync + plan_exit handling + recovery in rapid_loop"
```

---

### Task 11: WebSocket — plan_exit_confirmed + plan:clear

**Files:**
- Modify: `backend/app/api/routes/websocket.py`
- Modify: `backend/app/services/agent_service.py`

- [ ] **Step 1: Add `plan:exit_confirmed` handler in WebSocket route**

In `backend/app/api/routes/websocket.py`, add before the final `await _send_error(...)` block:

```python
            if msg_type == "plan:exit_confirmed":
                run_id = msg_data.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    await _send_error(websocket, code="invalid_request", message="run_id 不能为空")
                    continue
                try:
                    await agent_service.confirm_plan_exit(run_id)
                except ValueError as exc:
                    await _send_error(websocket, code="not_found", message=str(exc))
                continue

            if msg_type == "plan:clear":
                try:
                    plan_path = msg_data.get("path")
                    if plan_path and isinstance(plan_path, str):
                        from app.execution.plan_file_sync import PlanFileSync
                        PlanFileSync().delete(plan_path)
                    await websocket.send_json({
                        "type": "plan:cleared",
                        "data": {"path": plan_path},
                    })
                except Exception as exc:
                    await _send_error(websocket, code="internal_error", message=str(exc))
                continue
```

- [ ] **Step 2: Add `confirm_plan_exit` method to AgentService**

In `backend/app/services/agent_service.py`, add:

```python
    async def confirm_plan_exit(self, run_id: str) -> None:
        execution_loop = self._execution_loops.get(run_id)
        if execution_loop is None:
            raise ValueError(f"运行不存在: {run_id}")
        runtime = execution_loop._runtime
        if runtime is None:
            raise ValueError("运行未激活")
        # The context and runtime are accessed from the loop's internal state
        # This is safe because the loop is paused waiting for the confirmation
        context = None
        for key in self._runtime_adapters:
            adapter = self._runtime_adapters[key]
            if adapter.run_id == run_id:
                break
        await execution_loop.confirm_plan_exit_from_external(run_id)
```

Add a bridge method to `RapidExecutionLoop`:

```python
    async def confirm_plan_exit_from_external(self, run_id: str) -> None:
        """Called externally when user confirms plan_exit via WebSocket."""
        # This will be picked up by the main loop on next iteration
        if self._runtime is not None:
            self._runtime._plan_exit_confirmed = True
```

And check this flag in `_handle_planning`:

```python
    async def _handle_planning(self, context, result, rt):
        # Check for plan_exit confirmation
        if getattr(rt, '_plan_exit_confirmed', False):
            rt._plan_exit_confirmed = False
            await self.confirm_plan_exit(context, rt)
            # Continue normal planning with build mode
        # ... existing code ...
```

Also add `_plan_exit_confirmed = False` to RuntimeState's default.

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -v -k "websocket or agent_service" --timeout=30`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/websocket.py backend/app/services/agent_service.py backend/app/execution/rapid_loop.py backend/app/execution/models.py
git commit -m "feat: add plan_exit_confirmed + plan:clear WebSocket handlers"
```

---

### Task 12: Full Integration Test

**Files:**
- Modify: `backend/tests/test_execution/test_rapid_loop.py`

- [ ] **Step 1: Add integration test for stagnation detection**

```python
@pytest.mark.asyncio
async def test_stagnation_counter_increments_on_non_plan_tools(mock_llm, mock_tool_registry):
    """Verify that steps_since_last_plan_update increments when non-plan tools execute."""
    from app.execution.plan_engine import Plan, PlanStep
    from app.execution.context_manager import LoopContext

    context = LoopContext(task="test task", project_path="/tmp")
    context.plan = Plan(
        goal="test goal",
        steps=[PlanStep(id=1, description="Step 1", status="in_progress")],
        current_step_index=0,
    )
    context.metadata["steps_since_last_plan_update"] = 0

    executor = ToolCallExecutor(tool_registry=mock_tool_registry, emit=AsyncMock())

    # Execute a non-plan tool call
    tool_call = LLMToolCall(id="tc-1", name="grep", arguments={"pattern": "test"})
    await executor.execute(tool_call, context, 1)
    assert context.metadata["steps_since_last_plan_update"] == 1

    # Execute another non-plan tool call
    tool_call2 = LLMToolCall(id="tc-2", name="glob", arguments={"pattern": "*.py"})
    await executor.execute(tool_call2, context, 2)
    assert context.metadata["steps_since_last_plan_update"] == 2
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/test_execution/ -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_execution/test_rapid_loop.py
git commit -m "test: add integration test for plan stagnation detection"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Each design area covered by a task
- [x] **Placeholder scan:** No TBDs, TODOs, or "implement later"
- [x] **Type consistency:** Method names match across tasks (`confirm_plan_exit`, `steps_since_last_plan_update`, `plan_file_path`)
- [x] **Step_type removed:** Not in the plan (agreed to cut)
- [x] **LLM consistency checker removed:** Not in the plan (agreed to cut)
