# Plan Update Liveness — Root Cause Fix Design

## Problem

Plan tracking is not updated in real time during execution. The model frequently skips `plan.step_done` calls and either continues to the next step without updating or stops entirely without marking completion. Root cause analysis reveals three structural defects:

1. **Position weakness**: Execution plan section is last in system.txt (line 66/90), suffering from primacy effect dilution
2. **Injection rhythm gap**: Plan rules are injected once (system prompt), with no per-turn visibility — the model "forgets" plan updates when immersed in tool operations
3. **Behavior conflict**: Stopping rules (line 43, marked IMPORTANT) conflict with Plan rules — the model defaults to "stop" over "update plan first"

Secondary factors: skill injection may dilute plan instructions, context compression may lose plan state, tool results carry no plan status anchors.

## Reference: OpenCode Comparison

OpenCode's approach differs in key ways:
- **No per-turn todo injection**: opencode relies entirely on the model proactively calling `todowrite`; todo state is NOT re-injected per turn
- **TodoWrite in middle of system prompt**: anthropic.txt has Task Management section mid-prompt, not at top
- **SessionReminders infrastructure exists**: `session/reminders.ts` can append synthetic text to user messages, but currently only used for plan/build mode switching, NOT for todo state
- **No tool result hooks**: opencode tool results don't include todo/plan status

**Key insight**: ReflexionOS already has a MORE advanced mechanism than opencode — the stagnant detection (5/10/15 call gradient audits in `loop_message_builder.py:69-126`). The fix is not to reinvent but to supplement with three missing pieces.

---

## Fix Design

### P0 — System Prompt Reorder + Slim Down

**File**: `backend/app/execution/prompts/system.txt` (and `glm/system.txt`)

**Current section order** (90 lines):
```
1. Skill-first rule        (4-7)
2. Environment             (9-13)
3. How to use tools        (15-18)   ← removable
4. Core discipline         (20-29)   ← partially movable
5. Tool and shell rules    (31-41)   ← partially removable
6. Stopping rules          (43-54)   ← needs plan exception
7. Error handling          (56-59)
8. Communication           (61-64)
9. Execution plan          (66-90)   ← LAST, worst position
```

**New section order**:
```
1. Skill-first rule        (keep)
2. Execution plan          (moved from #9 → primacy position)
3. Plan > Stopping rule    (new — P4 fix)
4. Environment             (keep)
5. Core discipline         (slimmed: remove str_replace/patch/write details → moved to edit tool description)
6. Tool and shell rules    (slimmed: remove search-related rules → redundant with tool descriptions)
7. Stopping rules          (modified: add plan-active exception)
8. Error handling          (keep)
9. Communication           (keep)
```

**Specific removals**:
- Lines 15-18 ("How to use tools"): "You have access to the following tools. When you need to use a tool, simply call it. The system will handle the execution." — redundant; tool schemas are self-documenting
- Lines 25-29 (str_replace/patch/write rules): move to edit tool's description in tool registry, not system prompt
- Lines 37-39 (search-related rules): "Prefer targeted search (grep, glob) before large file reads" and "Avoid reading entire repositories..." — already in grep/glob/file tool descriptions
- Line 32-34 (GLM version "工具调用规则"): parameter name rules — these are model-specific and better handled by error recovery; remove from system prompt

**Estimated savings**: ~15-20 lines (~300-400 tokens)

### P1 — Per-Turn Plan Status Injection

**File**: `backend/app/execution/loop_message_builder.py`

**Mechanism**: When `context.plan is not None` and `context.plan.current_step` exists, append a lightweight plan status reminder to the Task Anchor user message (or create a standalone user message if no anchor is injected this turn).

**Format** (< 50 tokens):
```
[Plan ► Step 3/7: 实现用户认证模块] → complete → plan.step_done
```

**Implementation**:
1. In `LoopMessageBuilder.build()`, after the Task Anchor injection point (~line 176), before return
2. If `context.plan` and `context.plan.current_step` exist:
   - Build status string: `f"[Plan ► Step {step.id}/{total}: {step.description}] → complete → plan.step_done"`
   - Always create a new user message with the plan status (consistency and simplicity)
   - This increments `group_count` by 1 per turn — acceptable since it's once per LLM call cycle
3. Skip per-turn reminder when Plan Focus was just injected (check `_injected_focus_step_id == current_step_id` — Plan Focus is more detailed and already serves the purpose for that turn)

**Interaction with existing mechanisms**:
- Plan Focus (step switch injection): retains priority — when step switches, Focus message is more detailed; per-turn reminder skips that turn
- Stagnant detection (5/10/15 gradient): per-turn reminder is lightweight background; stagnant detection escalates with detailed audits. No conflict — they serve different purposes (awareness vs enforcement)

### P2 — Tool Result Plan Hook

**File**: `backend/app/execution/tool_call_executor.py`

**Mechanism**: When plan is active and the tool is not `plan` or `plan_exit`, append a plan status tag to the tool output before adding to context.

**Format** (< 30 tokens):
```
[Plan ► Step 3/7: 实现用户认证模块]
```

**Implementation**:
1. In `ToolCallExecutor.execute()`, after building `tool_output` (~line 155-169), before `context.add_message("tool", ...)`
2. Check: `context.plan is not None` and `context.plan.current_step is not None` and `tool_call.name not in ("plan", "plan_exit")`
3. Append: `tool_output += f"\n[Plan ► Step {step.id}/{total}: {step.description}]"`
4. This makes plan status visible in EVERY tool result, creating a persistent context anchor

**Token cost**: ~30 tokens per tool result. For a typical 20-step execution with 3 tool calls per step, that's ~1800 tokens total — negligible compared to the context window.

### P3 — Context Compression Plan Anchor Preservation

**File**: `backend/app/execution/prompts/midrun_compress_system.txt` (and `glm/midrun_compress_system.txt`)
**File**: `backend/app/execution/prompts/continuation_compress_system.txt` (and `glm/continuation_compress_system.txt`)

**midrun_compress changes**:
Add to the "Current progress" section requirement:
```
当前进度：<我们处于哪个步骤，还剩什么> (必须包含执行计划状态：当前 in_progress 的 step id 和描述、已完成 step 的关键 findings)
```

**continuation_compress changes**:
Expand "Current goal" line to include plan step:
```
当前目标：<一句话> (如执行计划存在，包含当前 step 信息)
```

### P4 — Stopping vs Plan Priority Resolution

**File**: `backend/app/execution/prompts/system.txt` (and `glm/system.txt`)

**New rule** (inserted after Execution plan section, before Environment):
```
Plan tracking overrides stopping. If a plan step was just completed, you MUST call plan.step_done BEFORE considering whether to stop. Stopping rules do not override the requirement to update the plan.
```

**Stopping rules modification**:
Add one bullet after the "IMPORTANT" header:
```
- When a plan is active, you MUST call plan.step_done/block before stopping — plan updates take priority over stopping.
```

---

## Files Changed Summary

| File | Change |
|------|--------|
| `prompts/system.txt` | Reorder sections, slim down, add plan>stopping rule |
| `prompts/glm/system.txt` | Same changes in Chinese |
| `loop_message_builder.py` | Add per-turn plan status injection in `build()` |
| `tool_call_executor.py` | Add plan status tag to non-plan tool results |
| `prompts/midrun_compress_system.txt` | Add plan state preservation requirement |
| `prompts/glm/midrun_compress_system.txt` | Same in Chinese |
| `prompts/continuation_compress_system.txt` | Add plan step to "Current goal" |
| `prompts/glm/continuation_compress_system.txt` | Same in Chinese |

## Risk Assessment

- **P0 (prompt reorder)**: Low risk — purely positional change. Verify by running existing prompt-related tests.
- **P1 (per-turn injection)**: Medium risk — adds ~50 tokens/turn. Need to ensure no infinite loop (plan status triggers plan status). Mitigated by: appending to existing user message, not creating new groups.
- **P2 (tool result hook)**: Low risk — adds ~30 tokens/tool result. Non-invasive string append. Tool output parsing is not affected (status tag is after JSON data).
- **P3 (compression)**: Low risk — instruction-only change to compression prompts.
- **P4 (priority rule)**: Low risk — explicit text rule. May slightly increase plan.step_done calls but that's the desired behavior.

## Testing

- `test_loop_message_builder.py`: Add tests for per-turn plan status injection
- `test_plan_tool.py`: Existing tests should still pass
- `test_runtime_tool_definitions.py`: Existing tests should still pass
- Manual integration test: run a multi-step task and verify plan.step_done is called after each step
