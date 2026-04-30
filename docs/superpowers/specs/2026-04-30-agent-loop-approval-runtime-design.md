# Agent Loop Approval Runtime Design

## Context

The current runtime assumes a tool call has only two meaningful outcomes:

- success
- failure

That model is too small for tools that need user approval. Shell commands, destructive file operations, patch deletion, browser actions, and future privileged tools all need a third outcome:

- waiting for user approval

The approval state cannot live only inside a tool. The Agent Loop must understand that a run is paused, not failed, and must be able to resume the same run after the user approves or denies the request.

The current code shape is:

- `ToolResult` has `success`, `output`, `error`, and `data`.
- `ToolCallExecutor` immediately executes a tool and projects success or failure into `LoopContext`.
- `RapidExecutionLoop` treats failed steps as error recovery inputs.
- `RunStatus` has `created`, `running`, `completed`, `failed`, and `cancelled`.
- The websocket protocol supports start, sync, and cancel, but no approval action.
- Conversation events persist tool start/result/error, but no approval state.

This design adds an approval-aware runtime layer before implementing tool-specific approval policies such as shell approval.

## Decision

Use scheme C:

> Pause the same run when approval is required, persist the pending approval, then resume the same run after user action.

Do not block a Python coroutine while waiting for the user. The run task should return a non-terminal waiting status. Resume should schedule a new async task for the same run and reconstruct context from persisted conversation state plus the approved tool result.

## Goals

- Add a generic approval mechanism for all tools.
- Preserve the same `run_id` across pause and resume.
- Treat approval waits as non-terminal run states, not failures.
- Persist enough approval state for frontend refresh and websocket reconnect.
- Execute approved stored tool calls, not model-supplied replacement payloads.
- Support allow-once, deny, and later trust-prefix actions.
- Keep tool-specific risk logic outside the Agent Loop.

## Non-Goals

- Implement shell command risk policy in this design.
- Persist long-lived project trust rules.
- Serialize live Python coroutine state.
- Add distributed or multi-user authorization.
- Add sandboxing.
- Build post-execution loop breaking in this phase.

## State Model

### RunStatus

Extend `RunStatus`:

```text
created
running
waiting_for_approval
resuming
completed
failed
cancelled
```

State transitions:

```text
created -> running
running -> waiting_for_approval
waiting_for_approval -> resuming
waiting_for_approval -> cancelled
resuming -> running
running -> completed
running -> failed
running -> cancelled
```

`waiting_for_approval` is non-terminal. The run has yielded control back to the app, but the task is not semantically complete.

### LoopStatus

Extend `LoopStatus`:

```text
WAITING_FOR_APPROVAL
RESUMING
```

`RapidExecutionLoop.run()` can return `WAITING_FOR_APPROVAL` without emitting `run:complete` or `run:error`.

### StepStatus

Extend `StepStatus`:

```text
PENDING
RUNNING
WAITING_FOR_APPROVAL
SUCCESS
FAILED
CANCELLED
```

The waiting step keeps the original `tool_call_id`, tool name, args, and approval id.

## Tool Result Model

Keep backward compatibility with existing tool results while adding an approval request payload.

```python
class ToolApprovalRequest(BaseModel):
    approval_id: str
    tool_name: str
    summary: str
    reasons: list[str] = []
    risks: list[str] = []
    payload: dict[str, Any] = {}
    suggested_action: str | None = None
    suggested_trust: dict[str, Any] | None = None


class ToolResult(BaseModel):
    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None
    approval_required: bool = False
    approval: ToolApprovalRequest | None = None
```

Rules:

- `approval_required=True` means the result is neither success nor normal failure.
- `ToolCallExecutor` must check `approval_required` before checking `success`.
- Approval requests should not enter normal error recovery.

## Pending Approval Model

Create a runtime approval store. The first implementation can be in memory, but it must project the state into conversation events so the frontend can recover pending approvals from a snapshot.

Suggested model:

```python
class PendingToolApproval(BaseModel):
    id: str
    session_id: str
    turn_id: str
    run_id: str
    step_number: int
    tool_call_id: str
    tool_name: str
    tool_arguments: dict[str, Any]
    approval_payload: dict[str, Any]
    status: Literal["pending", "approved", "denied", "expired", "stale"]
    created_at: datetime
    decided_at: datetime | None = None
    decision: Literal["allow_once", "deny", "trust_and_allow"] | None = None
```

Security rule:

> Approval execution uses the stored pending approval. User approval never accepts a new command, path, patch, or argument payload from the model.

## Runtime Flow

### Normal Tool Execution

```text
LLM returns tool call
ToolCallExecutor emits tool:start
Tool executes
ToolResult success/failure
ToolCallExecutor updates LoopContext
RapidExecutionLoop continues
```

### Approval Required

```text
LLM returns tool call
ToolCallExecutor emits tool:start
Tool returns approval_required
ToolCallExecutor stores PendingToolApproval
ToolCallExecutor emits approval:required
ToolCallExecutor returns a waiting step
RapidExecutionLoop sets loop status WAITING_FOR_APPROVAL
AgentService marks run waiting_for_approval
async task exits
```

No `run:complete` or `run:error` is emitted.

### Approve Once

```text
frontend sends conversation:approve_tool
AgentService loads PendingToolApproval
AgentService marks approval approved
AgentService marks run resuming
AgentService schedules resume for same run_id
resume execution runs the stored tool call
tool result is appended to context
loop continues from the same run
```

### Deny

```text
frontend sends conversation:deny_tool
AgentService marks approval denied
AgentService records a denied tool result
resume execution gives the denial result to the model
model can choose an alternative path or produce final answer
```

Denial is not a runtime failure. It is a user decision that becomes tool feedback.

## Resume Strategy

Do not resume by keeping the original coroutine alive.

Instead:

1. Persist the approval state through conversation events.
2. Store the pending tool call in `PendingApprovalStore`.
3. On approval, execute the stored tool call.
4. Reconstruct loop context from:
   - existing conversation history
   - the current task
   - the approved tool result
   - a system note that the run resumed after user approval
5. Continue the same run id.

This matches the current event-sourced conversation direction and keeps refresh/reconnect behavior tractable.

### Resume Input

Add an explicit resume input shape rather than overloading a fresh turn:

```python
class ResumeRunInput(BaseModel):
    run_id: str
    session_id: str
    turn_id: str
    approved_approval_id: str
    approved_tool_result: ToolResult | None = None
    denied_tool_result: ToolResult | None = None
```

`RapidExecutionLoop.run()` should accept an optional resume payload. When present:

- skip `InitialPlanBootstrapper.bootstrap()`
- keep the existing `run_id`
- rebuild context from conversation history
- add a system note that the run is resuming after user approval
- add the approved or denied tool result as a tool message associated with the original `tool_call_id`
- continue at the normal planning phase

The resume path should not create a new user turn, new run, or new initial plan.

### Tool Call Continuity

The original assistant tool call must be present in context before the resumed tool result. The current `LoopMessageBuilder` already preserves assistant/tool call groups when messages are present in order, so the approval flow must persist enough conversation events to reconstruct:

```text
assistant tool_call(original)
tool result(approved execution or user denial)
```

If the app cannot reconstruct that pair after restart, the approval should be marked expired and the user should retry the action instead of resuming with a dangling tool result.

## Conversation Events

Add event types:

```text
run.waiting_for_approval
run.resuming
approval.required
approval.approved
approval.denied
approval.stale
```

Event payload examples:

```json
{
  "approval_id": "approval-abc123",
  "tool_name": "shell",
  "step_number": 3,
  "summary": "Run shell command",
  "reasons": ["uses shell metacharacter: &&"],
  "risks": ["command will be interpreted by the local shell"],
  "payload": {
    "command": "pytest -q && git status --short",
    "cwd": "/project"
  },
  "actions": ["allow_once", "deny"]
}
```

`approval.required` should be visible in the conversation snapshot so the UI can restore the approval card after refresh.

## WebSocket/API Actions

Add websocket messages:

```text
conversation:approve_tool
conversation:deny_tool
conversation:trust_tool_prefix
```

Request payload:

```json
{
  "approval_id": "approval-abc123",
  "run_id": "run-123"
}
```

For trust actions:

```json
{
  "approval_id": "approval-abc123",
  "run_id": "run-123",
  "trust": {
    "scope": "session",
    "prefix": ["pytest"]
  }
}
```

The backend validates:

- approval exists
- approval belongs to the session
- approval belongs to the run
- run is `waiting_for_approval`
- approval is still pending

## Frontend UX

Add an approval card rendered from `approval.required`.

It should show:

- tool name
- summary
- arguments or safe payload summary
- reasons
- risks
- available actions
- stale/reapproval explanation when applicable

Actions:

- Allow once
- Trust for this session, when provided by the tool-specific policy
- Deny

The action receipt for a tool should support `waiting_for_approval` as a visible state.

## Interaction With Shell Approval

Shell approval becomes a tool-specific policy that plugs into this runtime.

Shell policy responsibilities:

- decide `allow`, `require_approval`, or `deny`
- classify shell risk
- suggest session trust rules
- attach environment snapshot

Approval runtime responsibilities:

- persist pending approval
- pause run
- emit approval events
- receive user decision
- resume same run

This separation keeps shell risk logic out of the Agent Loop.

## Error Handling

- If a pending approval is denied, record a tool result explaining the denial and continue the model loop.
- If a pending approval is stale, emit `approval.stale` and require a new decision.
- If a resumed tool execution fails, treat it as a normal tool failure.
- If the run is cancelled while waiting, mark the pending approval expired or cancelled.
- If the app restarts, in-memory pending approvals are lost in v1; persisted `approval.required` events should render as expired.

## Testing Strategy

Backend tests:

- Tool result with `approval_required=True` creates a waiting step.
- Waiting step does not trigger error recovery.
- Run transitions from `running` to `waiting_for_approval`.
- Approval required emits `approval.required` and `run.waiting_for_approval`.
- Approve once resumes the same run id.
- Deny records a tool denial result and resumes the same run id.
- Approval cannot execute replacement args.
- Cancel while waiting expires pending approval.

Frontend tests:

- Snapshot with pending approval renders approval card.
- Approval card sends approve action.
- Approval card sends deny action.
- Receipt displays waiting-for-approval state.
- Stale approval explains why a new confirmation is required.

Integration tests:

- A run pauses on approval and does not complete.
- Approval resumes the same run and continues to completion.
- Denial resumes the same run and lets the model choose another path.
- Refresh after approval required restores the pending approval UI.

## Rollout Plan

Phase 1: Approval Runtime Core

- Add run, loop, and step waiting states.
- Add approval-capable `ToolResult`.
- Add `PendingApprovalStore`.
- Add runtime events for approval required/approved/denied.
- Add websocket approval actions.
- Add frontend approval card.
- Test with a small test-only tool or shell mock.

Phase 2: Shell Integration

- Connect shell command policy to approval runtime.
- Support allow-once and deny.
- Add session trust after base approval flow is stable.

Phase 3: Consistency Layer

- Add stale environment handling.
- Add forced replan when a high-risk approval becomes stale.
- Add post-execution analyzer for repeated command loops and no-progress detection.

## Open Choices

Pending approvals can start in memory, but the event stream must expose enough state for the frontend to recover. If in-memory approval data is gone, the UI should mark the approval expired and ask the user to retry the action.

Trust-prefix persistence should remain session-only until a visible trust management UI exists.
