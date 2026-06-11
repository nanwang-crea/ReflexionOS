# Prompt Identity And Mode Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement layered prompt assembly with global/project `.reflexion` overlays, built-in coding mode, slimmer base prompts, and contract-based prompt tests.

**Architecture:** Keep the existing `PromptManager` API surface mostly intact, but extend it into a deterministic prompt assembler that merges built-in base prompts, optional global/project overlays, and a built-in coding appendix. Wire coding mode through the main execution loop only for normal build execution, keep planning prompts separate, and tighten final/error prompts so partial progress no longer looks like a valid completion path.

**Tech Stack:** Python 3.12, FastAPI runtime, Pydantic settings, pytest

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `backend/app/execution/prompt_manager.py` | Modify | Add overlay loading, layered system-prompt assembly, coding-mode prompt selection, and optional final-response mode awareness |
| `backend/app/execution/loop_message_builder.py` | Modify | Pass project root and coding mode into system/final prompt construction; remove hardcoded coding-agent final-summary identity |
| `backend/app/execution/rapid_loop.py` | Modify | Detect coding-mode execution context and pass it through runtime prompt generation |
| `backend/app/execution/prompts/system.txt` | Modify | Slim into base scaffold with general agent identity and non-redundant built-in protocol |
| `backend/app/execution/prompts/glm/system.txt` | Modify | Chinese-equivalent base scaffold |
| `backend/app/execution/prompts/coding_appendix.txt` | Create | English built-in coding-mode execution discipline |
| `backend/app/execution/prompts/glm/coding_appendix.txt` | Create | Chinese built-in coding-mode execution discipline |
| `backend/app/execution/prompts/final_response.txt` | Modify | Tighten final-answer gating with coding-mode verification closure |
| `backend/app/execution/prompts/glm/final_response.txt` | Modify | Chinese-equivalent final-answer gating |
| `backend/app/execution/prompts/error.txt` | Modify | Reinforce post-error continuation toward the same goal |
| `backend/app/execution/prompts/glm/error.txt` | Modify | Chinese-equivalent error continuation guidance |
| `backend/tests/test_execution/test_prompt_manager.py` | Modify | Replace coding-agent identity assertions with layered prompt contract tests |
| `backend/tests/test_execution/test_loop_message_builder.py` | Modify | Assert new system/final prompt assembly behavior from runtime call sites |
| `.reflexion/soul.md` | Create | Project-level identity/working-style overlay used for dogfooding the new prompt source |
| `.reflexion/agent.md` | Create | Project-level protocol overlay used for dogfooding the new prompt source |

---

### Task 1: Add Layered Prompt Assembly In `PromptManager`

**Files:**
- Modify: `backend/app/execution/prompt_manager.py`
- Test: `backend/tests/test_execution/test_prompt_manager.py`

- [ ] **Step 1: Write the failing tests for overlay-aware system prompts**

Add these tests near the top-level `TestPromptManager` coverage in `backend/tests/test_execution/test_prompt_manager.py`:

```python
from pathlib import Path


def test_get_system_prompt_uses_general_agent_identity(tmp_path, monkeypatch):
    manager = PromptManager(model_name="gpt-4o")

    prompt = manager.get_system_prompt(
        working_directory="/project",
        platform="darwin",
        is_git_repo=True,
    )

    assert "shared workspace" in prompt.lower() or "same project" in prompt.lower()
    assert "autonomous coding agent" not in prompt


def test_get_system_prompt_merges_global_and_project_overlays(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    (home / ".reflexion").mkdir(parents=True)
    (home / ".reflexion" / "soul.md").write_text("## Identity\nGlobal soul", encoding="utf-8")
    (home / ".reflexion" / "agent.md").write_text("## Evidence First\nGlobal agent", encoding="utf-8")

    project_root = tmp_path / "project"
    (project_root / ".reflexion").mkdir(parents=True)
    (project_root / ".reflexion" / "soul.md").write_text("## Identity\nProject soul", encoding="utf-8")
    (project_root / ".reflexion" / "agent.md").write_text("## Completion Rules\nProject agent", encoding="utf-8")

    manager = PromptManager(model_name="gpt-4o")
    prompt = manager.get_system_prompt(
        working_directory=str(project_root),
        platform="darwin",
        is_git_repo=False,
        project_root=str(project_root),
    )

    assert "Global soul" in prompt
    assert "Global agent" in prompt
    assert "Project soul" in prompt
    assert "Project agent" in prompt
    assert prompt.index("Global soul") < prompt.index("Project soul")


def test_get_system_prompt_skips_missing_overlay_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    project_root = tmp_path / "project"
    project_root.mkdir()

    manager = PromptManager(model_name="gpt-4o")
    prompt = manager.get_system_prompt(
        working_directory=str(project_root),
        platform="darwin",
        is_git_repo=False,
        project_root=str(project_root),
    )

    assert "Working directory" in prompt


def test_get_system_prompt_appends_coding_mode_rules(tmp_path):
    manager = PromptManager(model_name="gpt-4o")

    prompt = manager.get_system_prompt(
        working_directory="/project",
        platform="darwin",
        is_git_repo=True,
        coding_mode=True,
    )

    assert "When Coding Mode Applies" in prompt
    assert "status update is not completion" in prompt
    assert "unverified work remains unfinished work" in prompt
```

- [ ] **Step 2: Run the prompt-manager tests to verify they fail**

Run: `python -m pytest tests/test_execution/test_prompt_manager.py -v`

Expected: FAIL because `PromptManager.get_system_prompt()` does not yet accept `project_root` or `coding_mode`, and the old system prompt still says `autonomous coding agent`.

- [ ] **Step 3: Implement overlay loading helpers and layered assembly in `prompt_manager.py`**

Update `backend/app/execution/prompt_manager.py` with the following additions and signature changes:

```python
from pathlib import Path


class PromptManager:
    ...

    def _read_optional_text(self, path: Path) -> str:
        try:
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Failed to read prompt overlay: %s", path, exc_info=True)
        return ""

    def _overlay_paths(self, project_root: str | None) -> list[Path]:
        paths = [
            Path.home() / ".reflexion" / "soul.md",
            Path.home() / ".reflexion" / "agent.md",
        ]
        if project_root:
            root = Path(project_root)
            paths.extend([
                root / ".reflexion" / "soul.md",
                root / ".reflexion" / "agent.md",
            ])
        return paths

    @staticmethod
    def _join_sections(sections: list[str]) -> str:
        normalized = [section.strip() for section in sections if str(section or "").strip()]
        return "\n\n".join(normalized)

    def get_system_prompt(
        self,
        *,
        working_directory: str = "",
        platform: str = "",
        is_git_repo: bool = False,
        project_root: str | None = None,
        coding_mode: bool = False,
    ) -> str:
        base_prompt = self.get_template("system").render(
            working_directory=working_directory,
            platform=platform,
            date=datetime.now().strftime("%Y-%m-%d"),
            is_git_repo=str(is_git_repo),
        )
        overlays = [self._read_optional_text(path) for path in self._overlay_paths(project_root)]
        sections = [base_prompt, *overlays]
        if coding_mode:
            sections.append(self.get_template("coding_appendix").render())
        return self._join_sections(sections)
```

Also extend `TEMPLATES_MANIFEST` so the new `coding_appendix.txt` and `glm/coding_appendix.txt` files are loaded as family-specific templates with no variables.

- [ ] **Step 4: Run the prompt-manager tests to verify they pass**

Run: `python -m pytest tests/test_execution/test_prompt_manager.py -v`

Expected: PASS for the new overlay/coding-mode tests and any updated identity assertions.

---

### Task 2: Replace The Coding-Agent Base Identity And Add Built-In Coding Prompts

**Files:**
- Modify: `backend/app/execution/prompts/system.txt`
- Modify: `backend/app/execution/prompts/glm/system.txt`
- Create: `backend/app/execution/prompts/coding_appendix.txt`
- Create: `backend/app/execution/prompts/glm/coding_appendix.txt`
- Modify: `backend/tests/test_execution/test_prompt_manager.py`

- [ ] **Step 1: Write failing contract assertions for the new base prompt and coding appendix**

Add or replace tests in `backend/tests/test_execution/test_prompt_manager.py` with these contract checks:

```python
def test_default_family_uses_general_agent_prompt():
    manager = PromptManager(model_name="gpt-4o")
    prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)

    assert "shared workspace" in prompt.lower() or "same project" in prompt.lower()
    assert "autonomous coding agent" not in prompt
    assert "Instruction priority" in prompt
    assert "Clarification gate" in prompt


def test_glm_family_uses_general_agent_prompt_in_chinese():
    manager = PromptManager(model_name="glm-4-plus")
    prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)

    assert "协作" in prompt
    assert "自主编程智能体" not in prompt
    assert "指令优先级" in prompt
    assert "澄清门" in prompt


def test_coding_mode_prompt_adds_verification_contract():
    manager = PromptManager(model_name="glm-4-plus")
    prompt = manager.get_system_prompt(
        working_directory="/p",
        platform="darwin",
        is_git_repo=True,
        coding_mode=True,
    )

    assert "编码模式" in prompt or "coding mode" in prompt.lower()
    assert "未验证的工作仍然不算完成" in prompt or "unverified work remains unfinished work" in prompt
```

- [ ] **Step 2: Run the focused prompt-manager contract tests and verify they fail**

Run: `python -m pytest tests/test_execution/test_prompt_manager.py::TestPromptFamilySelection -v`

Expected: FAIL because the current prompt family files still declare a coding-agent identity and there is no coding appendix template.

- [ ] **Step 3: Rewrite the built-in prompt files with the new role split**

Set `backend/app/execution/prompts/system.txt` to a slimmer base scaffold like this:

```text
You are a pragmatic workspace agent collaborating with the user in the same project.
You help by investigating, reasoning, editing, verifying, and using tools when needed.

## Skill-first rule:
- If there is even a small chance that a skill applies to the current task, load it first using the 'skill' tool.

## Instruction priority:
- Follow the user's explicit instructions first.
- Then follow built-in safety and runtime protocol.
- Then follow any active runtime mode rules.
- Then follow project-level overlays.
- Then follow global overlays.
- Use the remaining system rules as defaults.

## Clarification gate:
- Default to action, not confirmation.
- If the answer can be obtained from code, files, tests, or available tools, investigate first.
- Only ask the user when the missing information can only come from user intent, approval, credentials, or unavailable external context.

## Core discipline:
- Observe -> plan -> act. Never edit a file you have not read first.
- Keep changes minimal and scoped to the user's request.
- Prefer a small correct change over a larger clever one.

## Tool and shell rules:
- The `shell` tool executes commands under an OS sandbox. Network access is blocked by default.
- NEVER run destructive commands unless explicitly requested by the user.

## Environment:
- Working directory: $working_directory
- Platform: $platform
- Today's date: $date
- Is directory a git repo: $is_git_repo
```

Create `backend/app/execution/prompts/coding_appendix.txt` with this content:

```text
## When Coding Mode Applies:
- Coding mode applies when the task requires code edits, bug fixes, test updates, build/test verification, or code-adjacent configuration changes.

## Execution Discipline:
- If work remains and no real blocker exists, continue in the same turn.
- A status update is not completion.
- Saying "X is fixed but Y remains" is not a valid stopping point.
- Do not defer remaining work to a later round unless user input is actually required.

## Verification Gate:
- After code changes, run the affected verification that the repository naturally requires.
- If build or test verification is relevant, keep going until it is run or a real blocker is identified.
- Unverified work remains unfinished work.

## Communication Constraints:
- Do not end with "if you want, I can continue" or equivalent handoff phrasing.
- Do not stop merely to report progress when the next implementation step is already clear.
```

Mirror the same meaning in `backend/app/execution/prompts/glm/system.txt` and `backend/app/execution/prompts/glm/coding_appendix.txt` in Chinese.

- [ ] **Step 4: Run prompt-manager tests to verify the rewritten prompt contracts pass**

Run: `python -m pytest tests/test_execution/test_prompt_manager.py -v`

Expected: PASS with the new general-agent identity and coding-mode contract assertions.

---

### Task 3: Wire Coding Mode Through Runtime Prompt Construction And Tighten Final/Error Prompts

**Files:**
- Modify: `backend/app/execution/loop_message_builder.py`
- Modify: `backend/app/execution/rapid_loop.py`
- Modify: `backend/app/execution/prompts/final_response.txt`
- Modify: `backend/app/execution/prompts/glm/final_response.txt`
- Modify: `backend/app/execution/prompts/error.txt`
- Modify: `backend/app/execution/prompts/glm/error.txt`
- Test: `backend/tests/test_execution/test_loop_message_builder.py`
- Test: `backend/tests/test_execution/test_prompt_manager.py`

- [ ] **Step 1: Write failing runtime-call-site tests for coding-mode-aware prompt assembly**

Add these tests to `backend/tests/test_execution/test_loop_message_builder.py`:

```python
def test_system_prompt_uses_general_agent_identity_from_runtime_builder():
    builder = build_message_builder()
    context = LoopContext(task="检查工具列表", project_path="/tmp/project")
    context.add_message("user", "检查工具列表")

    messages = builder.build(context)

    system_messages = [message for message in messages if message.role == "system"]
    assert "autonomous coding agent" not in system_messages[0].content
    assert "shared workspace" in system_messages[0].content.lower() or "same project" in system_messages[0].content.lower()


def test_build_final_summary_uses_non_coding_general_identity():
    builder = build_message_builder()
    context = LoopContext(task="总结工具结果")
    messages = builder.build_final_summary(context)

    assert "autonomous coding agent" not in (messages[0].content or "")
    assert "Do not call tools" in (messages[0].content or "")
```

Add one prompt-manager assertion for final responses:

```python
def test_final_response_prompt_warns_against_unverified_coding_completion(manager):
    prompt = manager.get_final_response_prompt(task="Fix the prompt stack")
    assert "required verification" in prompt.lower() or "未验证" in prompt
```

- [ ] **Step 2: Run the focused runtime prompt tests and verify they fail**

Run: `python -m pytest tests/test_execution/test_loop_message_builder.py tests/test_execution/test_prompt_manager.py -v`

Expected: FAIL because `build_final_summary()` still hardcodes `You are an autonomous coding agent` and the final response prompt does not mention verification closure.

- [ ] **Step 3: Pass coding-mode context through runtime prompt construction and tighten final/error prompts**

Apply the following minimal runtime changes:

```python
# backend/app/execution/loop_message_builder.py
system_prompt = self.prompt_manager.get_system_prompt(
    working_directory=context.project_path or os.getcwd(),
    platform=sys.platform,
    is_git_repo=os.path.isdir(os.path.join(context.project_path or os.getcwd(), ".git")),
    project_root=context.project_path,
    coding_mode=context.agent_mode != "plan",
)

# build_final_summary system preface
content=(
    "You are a pragmatic workspace agent. Write the final answer directly "
    "from the provided context. Do not call tools."
)
```

Also update `backend/app/execution/prompts/final_response.txt` to include lines like:

```text
- If relevant coding-mode verification has not been performed, do not claim the work is complete.
- If work still remains, continue execution instead of summarizing partial completion.
```

Update `backend/app/execution/prompts/error.txt` to include lines like:

```text
9. Do not turn this failure into a status-only summary when the task still has remaining work.
10. After fixing the tool-call issue, return to the same task objective.
```

Mirror the same meaning in `glm/final_response.txt` and `glm/error.txt`.

- [ ] **Step 4: Run the prompt/runtime tests to verify they pass**

Run: `python -m pytest tests/test_execution/test_prompt_manager.py tests/test_execution/test_loop_message_builder.py -v`

Expected: PASS with updated final-summary identity and coding-verification closure.

---

### Task 4: Add Project-Level `.reflexion` Dogfood Overlays And Finish Contract-Test Rewrite

**Files:**
- Create: `.reflexion/soul.md`
- Create: `.reflexion/agent.md`
- Modify: `backend/tests/test_execution/test_prompt_manager.py`
- Modify: `backend/tests/test_execution/test_loop_message_builder.py`

- [ ] **Step 1: Write failing tests that assert project overlays can appear in assembled prompts**

Add one focused test that uses the real repository convention in `backend/tests/test_execution/test_prompt_manager.py`:

```python
def test_project_reflexion_overlay_content_is_included(tmp_path):
    project_root = tmp_path / "project"
    (project_root / ".reflexion").mkdir(parents=True)
    (project_root / ".reflexion" / "soul.md").write_text("## Identity\nProject overlay identity", encoding="utf-8")
    (project_root / ".reflexion" / "agent.md").write_text("## Completion Rules\nProject overlay rules", encoding="utf-8")

    manager = PromptManager(model_name="gpt-4o")
    prompt = manager.get_system_prompt(
        working_directory=str(project_root),
        platform="darwin",
        is_git_repo=False,
        project_root=str(project_root),
    )

    assert "Project overlay identity" in prompt
    assert "Project overlay rules" in prompt
```

- [ ] **Step 2: Run the overlay-focused tests and verify they fail if project overlays are not yet fully assembled**

Run: `python -m pytest tests/test_execution/test_prompt_manager.py::test_project_reflexion_overlay_content_is_included -v`

Expected: FAIL before the project overlay files and assembly behavior are finalized.

- [ ] **Step 3: Add repository-level `.reflexion` overlay files for this project**

Create `.reflexion/soul.md` with content like:

```markdown
## Identity

You collaborate with the user inside the same workspace and help move software tasks forward through evidence and action.

## Working Style

- Be pragmatic and direct.
- Prefer understanding the codebase before acting.
- Do not pretend work is complete when it is not.

## Communication

- Keep updates brief and useful.
- Answer the real question once enough evidence exists.

## Quality Taste

- Prefer the smallest correct change.
- Respect existing patterns unless they block the task.
```

Create `.reflexion/agent.md` with content like:

```markdown
## Evidence First

- If code, tests, or repository state can answer the question, inspect them first.

## Skill And Mode Selection

- Load a relevant skill before acting when one plausibly applies.
- Treat code-editing work as coding mode and keep executing until complete or truly blocked.

## Completion Rules

- A progress report is not completion.
- If work remains and no real blocker exists, continue.

## Override Semantics

- Project-level `.reflexion` rules override global defaults for this repository.
```

- [ ] **Step 4: Run the full prompt-related test suite to verify the feature works end-to-end**

Run: `python -m pytest tests/test_execution/test_prompt_manager.py tests/test_execution/test_loop_message_builder.py -v`

Expected: PASS.

- [ ] **Step 5: Run a broader regression slice for execution prompt behavior**

Run: `python -m pytest tests/test_execution -v`

Expected: PASS, confirming no prompt/runtime regressions in adjacent execution-loop behavior.

---

## Self-Review Checklist

- Spec coverage: The tasks cover layered prompt assembly, dual `.reflexion` scopes, built-in coding mode, base prompt slimming, final/error tightening, runtime wiring, dogfood overlay files, and contract-test migration.
- Placeholder scan: No `TODO`, `TBD`, or content-free “write tests later” steps remain.
- Type consistency: `project_root` and `coding_mode` are introduced consistently as `get_system_prompt(...)` parameters and reused the same way in runtime tasks and tests.
