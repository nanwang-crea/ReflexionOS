# Prompt Identity And Mode Layering Design

> Date: 2026-06-10
> Status: Design
> Scope: Prompt architecture, runtime prompt assembly, project/global agent overlays, built-in coding mode

## 1. Goal

Upgrade ReflexionOS's prompt system from a single coding-agent-centered system prompt into a layered prompt architecture that:

- separates agent identity from execution discipline
- supports both global and project-level agent customization through `.reflexion/`
- treats coding as a built-in runtime mode rather than the top-level identity
- reduces prompt conflicts, duplicated rules, and unstable stop behavior
- preserves existing prompt families (`default`, `glm`) and existing execution-mode prompts (`plan_mode`, `final_response`, `error`)

This design is intended to make the agent more general-purpose at the top level while keeping coding tasks highly persistent, verifiable, and completion-oriented once the runtime enters coding mode.

## 2. Problem

The current prompt stack is structurally too flat:

1. The top-level system prompt defines the agent as an `autonomous coding agent` / `自主编程智能体`.
2. Identity, collaboration style, completion rules, mode-specific execution discipline, and communication constraints are all mixed into the same prompt layer.
3. Coding-specific anti-stop behavior is expressed as general personality, even though not all tasks are code-editing tasks.
4. The system has no first-class prompt source for user-level or project-level agent identity customization, despite already having project/global `.reflexion` concepts for plans, skills, memory, packages, and config.
5. Existing prompts can still allow a failure mode where the model accurately reports partial progress but ends the turn instead of continuing execution.

This creates three classes of issues:

- identity drift: the agent is over-specialized as a coding identity even when the task is analysis, explanation, planning, review, or diagnosis
- behavioral conflict: high-level collaboration guidance and low-level coding completion discipline can compete for priority
- prompt bloat: adding more anti-stop language directly into `system.txt` increases redundancy without clearly isolating responsibilities

## 3. Design Principles

The upgraded prompt architecture follows these principles:

1. Identity is not the same thing as execution mode.
2. Coding persistence is a runtime mode rule, not the entire personality.
3. Project-local agent behavior should override global defaults.
4. Built-in system safety and runtime protocol remain authoritative.
5. Prompt sections must have explicit responsibilities to minimize duplication and conflict.
6. Runtime assembly should use deterministic layering, not free-form concatenation of arbitrary documents.

## 4. High-Level Architecture

The prompt system is split into three conceptual layers:

1. Soul layer
2. Agent protocol layer
3. Built-in runtime mode layer

These layers are assembled on top of the existing built-in prompt scaffold and prompt family mechanism.

### 4.1 Soul Layer

The soul layer defines who the agent is and how it collaborates.

It covers:

- identity
- working style
- communication style
- quality taste
- evidence-based and pragmatic collaboration tone

It does not define tool schemas, plan state transitions, or mode-specific execution contracts.

### 4.2 Agent Protocol Layer

The agent layer defines the general runtime protocol that applies across tasks.

It covers:

- instruction priority
- evidence-first behavior
- skill and mode selection
- clarification gate
- blocker definition
- completion rules
- override semantics between built-in, global, and project overlays

It stays task-general. It must not fully duplicate coding-only execution rules.

### 4.3 Built-In Runtime Mode Layer

The mode layer defines stronger execution discipline for specific runtime contexts.

Phase 1 adds one built-in mode:

- coding mode

Future modes may include:

- debugging mode
- review mode
- research mode

Coding mode is conceptually a built-in skill, but in Phase 1 it is implemented as a built-in prompt appendix rather than a user-loadable external skill.

## 5. Prompt Sources And Scope

Prompt content will come from four source classes.

### 5.1 Built-In Runtime Prompt Sources

These remain under backend runtime control:

- `backend/app/execution/prompts/system.txt`
- `backend/app/execution/prompts/glm/system.txt`
- `backend/app/execution/prompts/plan_mode.txt`
- `backend/app/execution/prompts/final_response.txt`
- `backend/app/execution/prompts/error.txt`
- `backend/app/execution/prompts/coding_appendix.txt` (new)
- `backend/app/execution/prompts/glm/coding_appendix.txt` (new)

These files define built-in defaults, safety-critical rules, family-specific wording, and runtime-mode appendices.

### 5.2 Global Overlay Sources

These define user-level defaults across projects:

- `~/.reflexion/soul.md`
- `~/.reflexion/agent.md`

These files are optional. Missing files are silently ignored.

### 5.3 Project Overlay Sources

These define project-local overrides:

- `<project>/.reflexion/soul.md`
- `<project>/.reflexion/agent.md`

These files are optional. Missing files are silently ignored.

### 5.4 Runtime Environment Inputs

The existing runtime metadata remains injected programmatically:

- working directory
- platform
- date
- git repo flag

Environment metadata remains part of built-in prompt rendering and is not delegated to overlay files.

## 6. Layering And Priority

The runtime prompt assembly order must be deterministic.

### 6.1 Prompt Assembly Order

The final assembled system prompt is built in this order:

1. built-in base system scaffold
2. global soul overlay
3. global agent overlay
4. project soul overlay
5. project agent overlay
6. built-in runtime mode appendix, if active
7. environment block

This order ensures:

- built-in system protocol exists even without overlays
- global overlays define user defaults
- project overlays override global defaults for a specific workspace
- active mode rules strengthen the current execution context last
- environment metadata remains stable and non-overridable

### 6.2 Instruction Priority Semantics

Prompt content must express and preserve this semantic order:

1. user's explicit instructions
2. built-in safety and non-overridable runtime protocol
3. active runtime mode rules
4. project overlays
5. global overlays
6. built-in defaults

The agent-facing wording does not need to mirror this exact numbering verbatim, but runtime semantics and section responsibilities must preserve this meaning.

## 7. Responsibilities By File Type

### 7.1 `soul.md`

Allowed responsibilities:

- identity
- working style
- communication tone
- quality preferences
- collaboration posture

Disallowed responsibilities:

- tool parameter rules
- plan step state transitions
- final-answer gating mechanics
- coding-specific verification contracts
- shell/edit/tool safety protocol details

Recommended section structure:

- `Identity`
- `Working Style`
- `Communication`
- `Quality Taste`

### 7.2 `agent.md`

Allowed responsibilities:

- instruction priority
- evidence-first rule
- skill and mode selection principles
- clarification gate
- blocker definition
- completion rules
- override semantics

Disallowed responsibilities:

- tool schema duplication
- detailed coding-mode verification contract
- prompt-family-specific localization rules
- runtime environment block formatting

Recommended section structure:

- `Instruction Priority`
- `Evidence First`
- `Skill And Mode Selection`
- `Clarification Gate`
- `Blocker Definition`
- `Completion Rules`
- `Override Semantics`

### 7.3 `coding_appendix.txt`

Responsibilities:

- when coding mode applies
- coding-specific execution persistence
- coding-specific verification gate
- coding-specific communication constraints

Recommended section structure:

- `When Coding Mode Applies`
- `Execution Discipline`
- `Verification Gate`
- `Communication Constraints`

### 7.4 `system.txt`

After this redesign, `system.txt` becomes a slimmer base scaffold.

It should contain:

- base agent identity scaffold
- core built-in safety and system protocol
- skill-first and evidence-first entry rules
- assembly-compatible instruction priority framing
- environment block shell

It should not remain a dumping ground for all coding-specific or user-style-specific rules.

## 8. Coding Mode Design

Coding must no longer define the top-level agent identity. Instead, it becomes a built-in runtime mode.

### 8.1 When Coding Mode Applies

Coding mode activates when the runtime is handling tasks such as:

- code modification
- bug fixing
- feature implementation
- test updates
- configuration changes that require code-adjacent verification
- runs that have entered edit, patch, test, build, or validation-oriented shell execution

Coding mode does not activate for:

- pure Q&A
- code explanation only
- brainstorming/spec-writing only
- pure review without requested code changes
- pure repository exploration

### 8.2 Coding Mode Core Rules

Coding mode must strengthen the prompt with explicit anti-stop behavior:

- unfinished work without a real blocker must continue in the same turn
- a status update is not completion
- saying "X is fixed but Y remains" is not a valid stopping point
- do not defer remaining implementation or verification to "next round" unless user input is actually required
- unverified work remains unfinished work

### 8.3 Coding Mode Verification Gate

Coding mode must explicitly require:

- affected verification after code changes
- build/test execution when naturally required by the change scope
- no completion claim without verification evidence or an explicitly explained blocker

### 8.4 Coding Mode Communication Constraints

Coding mode must explicitly suppress handoff-style endings such as:

- "if you want, I can continue..."
- "next round I can..."
- status-only summaries used as the end of the turn when work remains

## 9. Conflict-Reduction Strategy

The main goal is not only to add new content, but to prevent prompt sections from fighting each other.

### 9.1 Primary Anti-Conflict Mechanism: Responsibility Segmentation

The first and most important conflict-reduction strategy is responsibility segmentation.

- soul overlays define collaboration identity, not execution protocol
- agent overlays define general protocol, not task-specific mode contracts
- coding appendix defines coding-specific execution contracts, not personality
- built-in runtime prompts define system-owned protocol and localization

This reduces overlap before assembly rather than trying to repair conflict after the fact.

### 9.2 Deterministic Layering

The second mechanism is deterministic assembly order.

Prompt sections must always be layered in the same order so that:

- global defaults are stable
- project context can reliably override global defaults
- mode rules are always applied after generic overlays

### 9.3 No Free-Form Whole-Document Override

Overlay files are not treated as unrestricted replacements for the built-in system prompt.

They are additive overlays with constrained responsibilities.

This avoids project-local files silently redefining low-level system safety, mode activation, or runtime protocol.

### 9.4 No Duplicate Full-Strength Rules Across Layers

Rules should be placed at the narrowest correct layer.

Examples:

- "be pragmatic and evidence-based" belongs in soul or base scaffold
- "only ask when user intent is truly missing" belongs in agent
- "do not stop after partial code progress" belongs in coding mode

Avoid repeating all three in every layer.

### 9.5 Built-In Rules Remain Canonical For Runtime Safety

Core safety and runtime mechanics remain built in and non-delegated:

- environment injection format
- tool/runtime safety floor
- family-specific localization structure
- final response gating protocol
- error recovery skeleton

## 10. PromptManager Changes

`PromptManager` should evolve from a plain template loader into a layered prompt assembler.

### 10.1 Phase 1 API Shape

The minimal Phase 1 change keeps the public entrypoint but extends it:

```python
get_system_prompt(
    *,
    working_directory: str = "",
    platform: str = "",
    is_git_repo: bool = False,
    project_root: str | None = None,
    coding_mode: bool = False,
) -> str
```

This avoids a large immediate refactor while enabling layered assembly.

### 10.2 Phase 1 Internal Responsibilities

Internally, `PromptManager` should:

1. resolve the prompt family (`default` or `glm`)
2. load the base system template
3. load optional global overlays
4. load optional project overlays
5. load optional coding appendix when `coding_mode=True`
6. assemble sections in deterministic order
7. append the rendered environment block
8. normalize spacing

### 10.3 Overlay Loading Behavior

Overlay files:

- are optional
- should be read as UTF-8 text when present
- should be skipped silently when absent
- should not crash prompt construction if a project has no `.reflexion/` directory

### 10.4 Light Normalization Only

The assembly stage should do only lightweight normalization:

- trim leading/trailing whitespace
- remove empty sections
- collapse repeated blank lines

It should not do heuristic semantic deduplication or LLM-style rewrite passes.

## 11. Built-In Prompt File Changes

### 11.1 `system.txt` / `glm/system.txt`

These files should be slimmed down and rewritten as base scaffolds.

Key changes:

- remove the top-level identity wording that narrowly defines the agent as a coding agent
- retain built-in runtime discipline that applies across tasks
- preserve skill-first, evidence-first, and clarification-gate style rules at a general level
- stop embedding full coding-mode anti-stop doctrine directly in the base scaffold

### 11.2 `coding_appendix.txt` / `glm/coding_appendix.txt`

These are new files.

They hold the coding-mode-specific execution contract and become the main home for:

- anti-stop coding rules
- verification-before-completion discipline
- communication constraints that prevent status-only handoffs

### 11.3 `final_response.txt`

This file should be tightened so final-answer generation also respects coding-mode closure.

It should reinforce that:

- if coding-mode work remains, continue instead of summarizing partial completion
- if required verification has not happened, completion cannot be claimed

### 11.4 `error.txt`

This file should be tightened so tool failures do not collapse execution into a status-only explanation mode.

It should reinforce that:

- the current objective remains active after a tool failure unless truly blocked
- fixing a tool-call issue should lead back into execution, not into premature wrap-up

### 11.5 `plan_mode.txt`

`plan_mode.txt` remains plan-specific and should not absorb coding-mode persistence rules.

Planning remains a separate execution state.

## 12. Runtime Integration

### 12.1 Main Runtime Prompt Construction

The main execution path currently builds prompts through `PromptManager` and `LoopMessageBuilder`.

Phase 1 integration should:

- pass `project_root` into system-prompt construction
- pass a `coding_mode` flag into system-prompt construction
- avoid large changes to plan-mode, compression, or final-summary calling structure in the same step unless needed

### 12.2 Coding Mode Activation Strategy

Phase 1 should use a conservative runtime activation strategy rather than a complex classifier.

Coding mode can be activated when:

- the user request clearly asks for code changes
- the run has entered edit/patch/test/build/validation behavior
- the current execution phase is code-modification-oriented

This is intentionally simpler than a full generalized mode router.

## 13. Testing Strategy

Prompt tests must shift from fixed-phrase identity assertions to contract assertions.

### 13.1 Replace Old Identity Assertions

Tests that assert the top-level prompt contains:

- `autonomous coding agent`
- `自主编程智能体`

should be replaced.

### 13.2 New Contract Assertions

Tests should verify:

- base system prompt expresses shared-workspace or pragmatic-agent collaboration framing rather than a coding-only identity
- coding mode injects anti-stop and verification rules
- coding mode and non-coding mode produce different prompt contracts
- GLM family receives semantically equivalent localized content
- missing overlay files do not break prompt generation
- project overlays override global overlays in the assembled prompt order

### 13.3 Keep Behavioral Focus

Tests should primarily verify the presence of required behavioral contracts rather than overfitting to one exact sentence.

The important contract is the runtime behavior the prompt is meant to enforce.

## 14. Implementation Phases

### Phase 1

- add global/project overlay loading for `soul.md` and `agent.md`
- add `coding_appendix.txt` and `glm/coding_appendix.txt`
- extend `PromptManager.get_system_prompt(...)` with `project_root` and `coding_mode`
- slim `system.txt` / `glm/system.txt`
- tighten `final_response.txt` and `error.txt`
- update prompt tests to assert new contracts

### Phase 2

- introduce more built-in runtime modes if needed (`review`, `debugging`)
- optionally refactor `PromptManager` into a more explicit prompt-assembly API
- optionally formalize overlay parsing/validation if free-form markdown starts drifting

## 15. Non-Goals

This design does not include:

- converting built-in modes into external user-loadable skills in Phase 1
- adding arbitrary semantic deduplication of overlay content
- allowing overlays to replace low-level runtime safety protocol
- redesigning the entire planning or compression subsystem in the same change

## 16. Expected Outcome

After this design is implemented:

- ReflexionOS will no longer be top-level-defined only as a coding identity
- agent personality and runtime execution contracts will be separated cleanly
- users will be able to set stable global defaults in `~/.reflexion/`
- projects will be able to override those defaults in `<project>/.reflexion/`
- coding tasks will still retain strong persistence and verification discipline through built-in coding mode
- prompt conflict and duplication pressure will be reduced by clear section ownership and deterministic assembly
