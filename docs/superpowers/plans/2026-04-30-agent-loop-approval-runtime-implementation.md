# Agent Loop Approval Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic tool approval runtime so a run can pause in `waiting_for_approval`, accept approve/deny actions, and resume the same run.

**Architecture:** Extend conversation/run models and events first, then teach `ToolCallExecutor` and `RapidExecutionLoop` to return a waiting result instead of failure. `AgentService` owns pending approvals and resume scheduling. Frontend renders `approval.required` from conversation events and sends approve/deny websocket actions.

**Tech Stack:** Python/FastAPI-style backend, Pydantic models, SQLAlchemy repositories, pytest, React/TypeScript, Zustand-style stores, Vitest.

---

## File Map

- Modify `backend/app/models/conversation.py`: add approval run/event/status enums.
- Modify `backend/app/execution/models.py`: add waiting loop/step status.
- Modify `backend/app/tools/base.py`: add `ToolApprovalRequest` and approval fields on `ToolResult`.
- Create `backend/app/execution/approval_store.py`: in-memory pending approval store and models.
- Modify `backend/app/execution/tool_call_executor.py`: detect `approval_required`, create waiting step, emit approval event.
- Modify `backend/app/execution/rapid_loop.py`: stop loop cleanly on waiting step and return `WAITING_FOR_APPROVAL`.
- Modify `backend/app/services/conversation_projection.py`: project `run.waiting_for_approval`, `run.resuming`, and approval payload updates.
- Modify `backend/app/services/conversation_runtime_adapter.py`: translate runtime approval events into conversation events.
- Modify `backend/app/services/agent_service.py`: own approval store, expose approve/deny websocket handlers, schedule same-run resume placeholder.
- Modify `backend/app/api/routes/websocket.py`: accept approve/deny messages.
- Modify `frontend/src/services/sessionConversationWebSocket.ts`: add approve/deny message helpers and events.
- Modify `frontend/src/types/conversation.ts`: add approval payload types.
- Modify `frontend/src/features/conversation/conversationReducer.ts`: preserve approval tool trace payloads.
- Modify `frontend/src/components/execution/ActionReceipt.tsx` and `frontend/src/components/execution/receiptUtils.ts`: display waiting-for-approval state.

## Task 1: Backend Models, Projection, and Approval Store

**Files:**
- Modify: `backend/app/models/conversation.py`
- Modify: `backend/app/execution/models.py`
- Modify: `backend/app/tools/base.py`
- Create: `backend/app/execution/approval_store.py`
- Modify: `backend/app/services/conversation_projection.py`
- Test: `backend/tests/test_services/test_conversation_projection.py`
- Test: `backend/tests/test_execution/test_approval_store.py`

- [ ] **Step 1: Write failing projection tests**

Add tests asserting:

```python
def test_projection_run_waiting_for_approval_keeps_turn_active(tmp_path):
    ...
    projection.apply(... EventType.RUN_WAITING_FOR_APPROVAL ...)
    assert run.status == RunStatus.WAITING_FOR_APPROVAL
    assert turn.status == TurnStatus.RUNNING
    assert session.active_turn_id == "turn-1"
```

and:

```python
def test_projection_run_resuming_sets_run_resuming_and_keeps_turn_active(tmp_path):
    ...
    projection.apply(... EventType.RUN_RESUMING ...)
    assert run.status == RunStatus.RESUMING
    assert turn.status == TurnStatus.RUNNING
```

- [ ] **Step 2: Run projection tests and confirm they fail**

Run:

```bash
cd backend && pytest tests/test_services/test_conversation_projection.py -q
```

Expected: fail because new enum values/events do not exist.

- [ ] **Step 3: Implement model and projection support**

Add enum values:

```python
RunStatus.WAITING_FOR_APPROVAL = "waiting_for_approval"
RunStatus.RESUMING = "resuming"
EventType.RUN_WAITING_FOR_APPROVAL = "run.waiting_for_approval"
EventType.RUN_RESUMING = "run.resuming"
EventType.APPROVAL_REQUIRED = "approval.required"
EventType.APPROVAL_APPROVED = "approval.approved"
EventType.APPROVAL_DENIED = "approval.denied"
EventType.APPROVAL_STALE = "approval.stale"
```

Add loop/step statuses:

```python
LoopStatus.WAITING_FOR_APPROVAL = "waiting_for_approval"
LoopStatus.RESUMING = "resuming"
StepStatus.WAITING_FOR_APPROVAL = "waiting_for_approval"
```

Add `ToolApprovalRequest` and `approval_required` fields to `ToolResult`.

Project `RUN_WAITING_FOR_APPROVAL` and `RUN_RESUMING` by updating only the run status and preserving active turn/session state.

- [ ] **Step 4: Add approval store tests**

Create tests for:

```python
store = PendingApprovalStore()
pending = store.create(...)
assert store.get(pending.id).status == "pending"
assert store.approve(pending.id, decision="allow_once").status == "approved"
assert store.deny(pending.id).status == "denied"
```

- [ ] **Step 5: Implement approval store**

Create focused Pydantic model `PendingToolApproval` and thread-safe in-memory `PendingApprovalStore` with `create`, `get`, `approve`, `deny`, `expire_for_run`.

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend && pytest tests/test_services/test_conversation_projection.py tests/test_execution/test_approval_store.py -q
```

Expected: pass.

## Task 2: Runtime Waiting Outcome

**Files:**
- Modify: `backend/app/execution/tool_call_executor.py`
- Modify: `backend/app/execution/rapid_loop.py`
- Test: `backend/tests/test_execution/test_rapid_loop.py`

- [ ] **Step 1: Write failing rapid loop test**

Add a fake tool that returns:

```python
ToolResult(
    success=False,
    approval_required=True,
    approval=ToolApprovalRequest(
        approval_id="approval-1",
        tool_name="approval_tool",
        summary="需要审批",
        payload={"value": 1},
    ),
)
```

Assert:

```python
result.status == LoopStatus.WAITING_FOR_APPROVAL
result.steps[-1].status == StepStatus.WAITING_FOR_APPROVAL
emitted event types include "approval:required"
emitted event types do not include "tool:error"
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
cd backend && pytest tests/test_execution/test_rapid_loop.py -q
```

Expected: fail because approval result is treated as failed.

- [ ] **Step 3: Implement waiting outcome**

Update `ToolCallExecutor.execute()` to check `result.approval_required` first:

- set step status to `WAITING_FOR_APPROVAL`
- set step output to approval summary
- add approval id in step data if a data field is added, otherwise include in output/error metadata
- emit `approval:required` with tool name, arguments, step number, and approval payload
- do not add normal tool message to LLM context yet

Update `RapidExecutionLoop` to:

- return `LoopStatus.WAITING_FOR_APPROVAL`
- emit no terminal run event
- skip error recovery for waiting steps

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend && pytest tests/test_execution/test_rapid_loop.py -q
```

Expected: pass.

## Task 3: Conversation Adapter and AgentService Approval Actions

**Files:**
- Modify: `backend/app/services/conversation_runtime_adapter.py`
- Modify: `backend/app/services/agent_service.py`
- Modify: `backend/app/api/routes/websocket.py`
- Test: `backend/tests/test_services/test_conversation_runtime_adapter.py`
- Test: `backend/tests/test_api/test_conversation_websocket.py`

- [ ] **Step 1: Write failing adapter test**

Assert `approval:required` produces:

- `message.payload_updated` with tool trace status `waiting_for_approval`
- `approval.required`
- `run.waiting_for_approval`

- [ ] **Step 2: Implement adapter events**

Map runtime `approval:required` into conversation events. Keep the existing tool trace message and update its payload status to `waiting_for_approval`.

- [ ] **Step 3: Write failing websocket action tests**

Add tests that websocket messages:

```json
{"type":"conversation:approve_tool","data":{"approval_id":"approval-1","run_id":"run-1"}}
{"type":"conversation:deny_tool","data":{"approval_id":"approval-1","run_id":"run-1"}}
```

call `AgentService.approve_tool_call(...)` or `AgentService.deny_tool_call(...)`.

- [ ] **Step 4: Implement AgentService and websocket handlers**

Add methods:

```python
async def approve_tool_call(self, *, session_id: str, run_id: str, approval_id: str) -> None
async def deny_tool_call(self, *, session_id: str, run_id: str, approval_id: str) -> None
```

First implementation may emit approval approved/denied and run resuming events without full shell execution resume. It must validate run/session and pending status.

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend && pytest tests/test_services/test_conversation_runtime_adapter.py tests/test_api/test_conversation_websocket.py -q
```

Expected: pass.

## Task 4: Frontend Approval Display and Actions

**Files:**
- Modify: `frontend/src/services/sessionConversationWebSocket.ts`
- Modify: `frontend/src/types/conversation.ts`
- Modify: `frontend/src/components/execution/receiptUtils.ts`
- Modify: `frontend/src/components/execution/ActionReceipt.tsx`
- Test: `frontend/src/components/execution/receiptUtils.test.ts` if existing, otherwise `frontend/src/features/conversation/conversationReducer.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Assert:

- receipt details can represent status `waiting_for_approval`
- summary text is stable for approval-required shell/tool traces
- websocket service sends `conversation:approve_tool` and `conversation:deny_tool`

- [ ] **Step 2: Implement websocket helpers**

Add:

```ts
approveTool(payload: { runId: string; approvalId: string }): void
denyTool(payload: { runId: string; approvalId: string }): void
```

- [ ] **Step 3: Implement receipt status support**

Add `waiting_for_approval` to receipt status types and render it as a non-terminal waiting state.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd frontend && pnpm test -- --run
```

Expected: pass.

## Final Verification

- [ ] Run backend targeted tests:

```bash
cd backend && pytest tests/test_execution/test_rapid_loop.py tests/test_services/test_conversation_projection.py tests/test_services/test_conversation_runtime_adapter.py tests/test_api/test_conversation_websocket.py -q
```

- [ ] Run frontend targeted tests:

```bash
cd frontend && pnpm test -- --run
```

- [ ] Check git status and summarize remaining work.
