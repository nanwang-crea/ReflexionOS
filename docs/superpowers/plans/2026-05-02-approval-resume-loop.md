# Approval Resume Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user approves a tool call, resume the `RapidExecutionLoop` so the agent continues executing subsequent steps instead of terminating the run.

**Architecture:** `RapidExecutionLoop.run()` suspends on an `asyncio.Event` when a step enters `WAITING_FOR_APPROVAL`. `_decide_tool_call_approval` writes the approval result into the loop's context and sets the event to wake it. The loop then continues its `while` cycle — LLM gets the tool result, decides next actions, and the run completes naturally.

**Tech Stack:** Python 3.12, asyncio, Pydantic, pytest

---

## File Map

- **Modify** `backend/app/execution/rapid_loop.py` — Suspend on `asyncio.Event` instead of breaking; resume and inject approval result
- **Modify** `backend/app/execution/tool_call_executor.py` — Return approval step with enough metadata for resume
- **Modify** `backend/app/services/agent_service.py` — Wake the loop on approval instead of terminating the run; handle deny
- **Modify** `backend/app/services/conversation_runtime_adapter.py` — Handle `run:resuming` runtime event
- **Modify** `backend/tests/test_execution/test_rapid_loop.py` — Test loop suspend/resume
- **Modify** `backend/tests/test_services/test_agent_service.py` — Test approval resumes loop; deny cancels loop

---

## Task 1: RapidExecutionLoop Suspend/Resume on Approval

**Files:**
- Modify: `backend/app/execution/rapid_loop.py`

The loop currently breaks out of the `while` loop when a step enters `WAITING_FOR_APPROVAL`. Instead, it should suspend on an `asyncio.Event`, and when woken, inject the approval result into `LoopContext` and continue.

- [ ] **Step 1: Add resume infrastructure to RapidExecutionLoop**

In `backend/app/execution/rapid_loop.py`, add these attributes to `__init__`:

```python
        self._approval_resume_event: asyncio.Event | None = None
        self._approval_result: dict | None = None
```

Add these public methods to `RapidExecutionLoop`:

```python
    def get_approval_resume_event(self) -> asyncio.Event:
        if self._approval_resume_event is None:
            self._approval_resume_event = asyncio.Event()
        return self._approval_resume_event

    def set_approval_result(self, result: dict) -> None:
        self._approval_result = result
        event = self._approval_resume_event
        if event is not None:
            event.set()
```

- [ ] **Step 2: Replace break with suspend in the TOOL_EXECUTION block**

In `RapidExecutionLoop.run()`, replace the `WAITING_FOR_APPROVAL` block (currently lines 176-179):

```python
                if step.status == StepStatus.WAITING_FOR_APPROVAL:
                    loop_result.status = LoopStatus.WAITING_FOR_APPROVAL
                    loop_result.result = step.output
                    state = LoopPhase.DONE
                    break
```

With:

```python
                if step.status == StepStatus.WAITING_FOR_APPROVAL:
                    loop_result.status = LoopStatus.WAITING_FOR_APPROVAL
                    loop_result.result = step.output

                    await self._emit(
                        "run:waiting_for_approval",
                        {
                            "run_id": loop_result.id,
                            "approval_id": step.approval_id,
                            "step_number": step.step_number,
                            "tool_name": step.tool,
                        },
                    )

                    resume_event = self.get_approval_resume_event()
                    await resume_event.wait()

                    approval_result = self._approval_result
                    self._approval_result = None
                    self._approval_resume_event = asyncio.Event()

                    if approval_result is not None:
                        loop_result.status = LoopStatus.RESUMING

                        tool_output = approval_result.get("output") or approval_result.get("error") or ""
                        context.add_message(
                            "tool",
                            content=tool_output,
                            tool_call_id=step.tool_call_id,
                        )
                        context.update_history(step, tool_output)

                        step.status = StepStatus.SUCCESS if approval_result.get("success") else StepStatus.FAILED
                        step.output = approval_result.get("output")
                        step.error = approval_result.get("error")

                        await self._emit(
                            "run:resuming",
                            {
                                "run_id": loop_result.id,
                                "approval_id": step.approval_id,
                                "execution_success": approval_result.get("success"),
                            },
                        )

                        state = LoopPhase.PLANNING
                        self.has_executed_tools = True
                    else:
                        loop_result.status = LoopStatus.CANCELLED
                        loop_result.result = "审批被拒绝"
                        state = LoopPhase.DONE
```

Also add the `run:waiting_for_approval` and `run:resuming` handling in the `finally` block. Currently the `finally` block emits `run:complete` unless the status is `CANCELLED` or `WAITING_FOR_APPROVAL`. After resume, the loop should continue and eventually reach a terminal status normally. Update the `finally` block condition:

```python
        if loop_result.status not in {
            LoopStatus.CANCELLED,
            LoopStatus.WAITING_FOR_APPROVAL,
        }:
```

This stays the same — after resume, `loop_result.status` will be `RESUMING` briefly, then transition to `RUNNING`, and eventually `COMPLETED`. The `run:complete` event will fire at the right time.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_execution/test_rapid_loop.py -v`

Expected: PASS — existing tests don't hit the resume path (they just check `WAITING_FOR_APPROVAL` status)

- [ ] **Step 4: Commit**

```bash
git add backend/app/execution/rapid_loop.py
git commit -m "feat: suspend RapidExecutionLoop on approval instead of breaking"
```

---

## Task 2: ConversationRuntimeAdapter Handles run:resuming

**Files:**
- Modify: `backend/app/services/conversation_runtime_adapter.py`

The adapter needs to handle the new `run:resuming` runtime event by emitting `RUN_RESUMING` conversation event. It also needs to handle `run:waiting_for_approval` (distinct from the existing `approval:required` which is a tool-level event).

- [ ] **Step 1: Add handler for `run:resuming` in `handle_event`**

In `ConversationRuntimeAdapter.handle_event`, add a case after the `approval:required` handler:

```python
        if event_type == "run:resuming":
            return self._append_events(self._run_resuming_events(data))
```

- [ ] **Step 2: Add the `_run_resuming_events` method**

```python
    def _run_resuming_events(self, data: dict) -> list[ConversationEvent]:
        return [
            self._new_event(
                event_type=EventType.RUN_RESUMING,
                run_id=self.run_id,
                payload_json={
                    "approval_id": data.get("approval_id"),
                    "execution_success": data.get("execution_success"),
                },
            ),
        ]
```

- [ ] **Step 3: Run adapter tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_services/test_conversation_projection.py -v`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/conversation_runtime_adapter.py
git commit -m "feat: handle run:resuming event in ConversationRuntimeAdapter"
```

---

## Task 3: AgentService Resumes Loop on Approval

**Files:**
- Modify: `backend/app/services/agent_service.py`

This is the core change. `_decide_tool_call_approval` must now wake the suspended loop instead of terminating the run.

- [ ] **Step 1: Store the execution loop reference during _run_turn**

In `_run_turn`, after creating the `execution_loop`, store it in a dict keyed by `run_id`:

Add a new instance variable in `AgentService.__init__`:

```python
        self._execution_loops: dict[str, RapidExecutionLoop] = {}
```

In `_run_turn`, after creating the loop (line ~318), store it:

```python
        run_tool_registry = self._build_run_tool_registry(project_path)
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=run_tool_registry,
            event_callback=event_callback,
        )
        self._execution_loops[run_id] = execution_loop
```

In the `finally` block of `_run_turn`, clean it up:

```python
        finally:
            self._runtime_adapters.pop(run_id, None)
            self._execution_loops.pop(run_id, None)
```

- [ ] **Step 2: Rewrite `_decide_tool_call_approval` approve path to resume loop**

Replace the entire approve block in `_decide_tool_call_approval` (the `if approval_event_type == EventType.APPROVAL_APPROVED:` branch):

Old:
```python
            if approval_event_type == EventType.APPROVAL_APPROVED:
                self.pending_approval_store.approve(approval_id)
                trace_status = "approved"
                terminal_event_type = EventType.RUN_COMPLETED

                execution_result = await self._execute_approved_tool(pending)

                terminal_payload = {
                    "finished_at": datetime.now().isoformat(),
                    "result": "approval_executed",
                    "execution_success": execution_result.success,
                    "execution_output": execution_result.output,
                    "execution_error": execution_result.error,
                }
```

New:
```python
            if approval_event_type == EventType.APPROVAL_APPROVED:
                self.pending_approval_store.approve(approval_id)
                trace_status = "approved"

                execution_result = await self._execute_approved_tool(pending)

                loop = self._execution_loops.get(run_id)
                if loop is not None:
                    loop.set_approval_result({
                        "success": execution_result.success,
                        "output": execution_result.output,
                        "error": execution_result.error,
                    })

                    events_to_append.extend(
                        [
                            ConversationEvent(
                                id=f"evt-{uuid4().hex[:8]}",
                                session_id=session_id,
                                turn_id=run.turn_id,
                                run_id=run_id,
                                event_type=approval_event_type,
                                payload_json={"approval_id": approval_id},
                            ),
                        ],
                    )

                    return
                else:
                    terminal_event_type = EventType.RUN_COMPLETED
                    terminal_payload = {
                        "finished_at": datetime.now().isoformat(),
                        "result": "approval_executed_no_loop",
                        "execution_success": execution_result.success,
                        "execution_output": execution_result.output,
                        "execution_error": execution_result.error,
                    }
```

For the deny path, also wake the loop so it can exit cleanly:

Old deny block:
```python
            else:
                self.pending_approval_store.deny(approval_id)
                trace_status = "denied"
                terminal_event_type = EventType.RUN_CANCELLED
                terminal_payload = {
                    "finished_at": datetime.now().isoformat(),
                    "reason": "approval_denied",
                }
```

New deny block:
```python
            else:
                self.pending_approval_store.deny(approval_id)
                trace_status = "denied"

                loop = self._execution_loops.get(run_id)
                if loop is not None:
                    loop.set_approval_result(None)

                    events_to_append.extend(
                        [
                            ConversationEvent(
                                id=f"evt-{uuid4().hex[:8]}",
                                session_id=session_id,
                                turn_id=run.turn_id,
                                run_id=run_id,
                                event_type=approval_event_type,
                                payload_json={"approval_id": approval_id},
                            ),
                        ],
                    )

                    return
                else:
                    terminal_event_type = EventType.RUN_CANCELLED
                    terminal_payload = {
                        "finished_at": datetime.now().isoformat(),
                        "reason": "approval_denied",
                    }
```

The key insight: when the loop is alive, we set the approval result on it and return immediately (no terminal event). The loop wakes up, handles the result, and eventually terminates on its own — emitting `run:complete` or `run:cancelled` through the normal `finally` block. When the loop is NOT alive (edge case: task was lost), we fall back to the old terminal-event behavior.

- [ ] **Step 3: Remove `terminal_event_type` and `terminal_payload` from the shared path**

Since the approve/deny paths now both handle the terminal event themselves (either early-return when loop exists, or set the terminal vars when loop is absent), the shared code at the bottom that appends `approval_event_type` and `terminal_event_type` events needs to handle the case where these variables may not be set.

Refactor the bottom section. The current code after the if/else block:

```python
        trace_message = self._find_pending_approval_trace_message(...)
        events_to_append: list[ConversationEvent] = []
        if trace_message is not None:
            events_to_append.append(...)

        events_to_append.extend(
            [
                ConversationEvent(...approval_event_type...),
                ConversationEvent(...terminal_event_type...),
            ],
        )
        events = self.conversation_service._append_events_locked(session_id, events_to_append)
        await self._broadcast_conversation_events(session_id=session_id, events=events)
```

Replace with:

```python
        trace_message = self._find_pending_approval_trace_message(
            run_id=run_id,
            approval_id=approval_id,
        )
        events_to_append: list[ConversationEvent] = []
        if trace_message is not None:
            events_to_append.append(
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=run.turn_id,
                    run_id=run_id,
                    message_id=trace_message.id,
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    payload_json={
                        "payload_json": {
                            "approval_id": approval_id,
                            "status": trace_status,
                        }
                    },
                )
            )

        if terminal_event_type is not None:
            events_to_append.append(
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=run.turn_id,
                    run_id=run_id,
                    event_type=terminal_event_type,
                    payload_json=terminal_payload,
                )
            )

        if events_to_append:
            events = self.conversation_service._append_events_locked(session_id, events_to_append)
            await self._broadcast_conversation_events(session_id=session_id, events=events)
```

Also, initialize `terminal_event_type` and `terminal_payload` before the if/else block:

```python
        terminal_event_type: EventType | None = None
        terminal_payload: dict | None = None
```

- [ ] **Step 4: Run existing tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_services/test_agent_service.py -v`

Expected: Some tests may need updating — particularly the parametrized approval test that expects `RUN_COMPLETED` as the last event. When the loop is not alive (which is the case in the test — there's no actual execution loop running), the fallback path emits `RUN_COMPLETED` as before, so it should still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent_service.py
git commit -m "feat: resume execution loop on approval instead of terminating run"
```

---

## Task 4: Test Loop Suspend/Resume in RapidExecutionLoop

**Files:**
- Modify: `backend/tests/test_execution/test_rapid_loop.py`

- [ ] **Step 1: Write test for approval resume in loop**

Add this test to `TestRapidExecutionLoop`:

```python
    @pytest.mark.asyncio
    async def test_approval_resume_continues_loop_execution(self, mock_llm):
        """When approval is granted, the loop resumes and continues executing."""
        registry = ToolRegistry()
        registry.register(ApprovalTool())
        registry.register(MockTool())
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=5,
            event_callback=callback,
        )

        approval_tool_call = LLMToolCall(name="approval_tool", arguments={"value": 1})
        mock_tool_call = LLMToolCall(name="mock", arguments={"path": "."})

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="需要审批",
                    tool_calls=[approval_tool_call],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            elif call_count[0] == 2:
                async for chunk in self._stream_response(
                    content="审批通过，继续执行",
                    tool_calls=[mock_tool_call],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="任务完成"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        async def resume_after_delay():
            await asyncio.sleep(0.1)
            execution_loop.set_approval_result({
                "success": True,
                "output": "approved output",
                "error": None,
            })

        asyncio.get_event_loop().create_task(resume_after_delay())

        result = await execution_loop.run("需要审批的任务")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 2
        assert result.steps[0].status == StepStatus.SUCCESS
        assert result.steps[0].tool == "approval_tool"
        assert result.steps[1].tool == "mock"
        assert call_count[0] == 3

        event_types = [event["type"] for event in events]
        assert "run:waiting_for_approval" in event_types
        assert "run:resuming" in event_types
        assert "run:complete" in event_types
```

- [ ] **Step 2: Write test for approval deny cancels loop**

```python
    @pytest.mark.asyncio
    async def test_approval_deny_cancels_loop_execution(self, mock_llm):
        """When approval is denied, the loop cancels."""
        registry = ToolRegistry()
        registry.register(ApprovalTool())
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=5,
            event_callback=callback,
        )

        approval_tool_call = LLMToolCall(name="approval_tool", arguments={"value": 1})

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                content="需要审批",
                tool_calls=[approval_tool_call],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        async def deny_after_delay():
            await asyncio.sleep(0.1)
            execution_loop.set_approval_result(None)

        asyncio.get_event_loop().create_task(deny_after_delay())

        result = await execution_loop.run("需要审批的任务")

        assert result.status == LoopStatus.CANCELLED
        assert result.result == "审批被拒绝"

        event_types = [event["type"] for event in events]
        assert "run:waiting_for_approval" in event_types
        assert "run:complete" not in event_types
```

- [ ] **Step 3: Run the new tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_execution/test_rapid_loop.py::TestRapidExecutionLoop::test_approval_resume_continues_loop_execution tests/test_execution/test_rapid_loop.py::TestRapidExecutionLoop::test_approval_deny_cancels_loop_execution -v`

Expected: PASS

- [ ] **Step 4: Run full rapid loop tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_execution/test_rapid_loop.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_execution/test_rapid_loop.py
git commit -m "test: add loop suspend/resume and deny tests for RapidExecutionLoop"
```

---

## Task 5: Test AgentService Approval Resumes Loop End-to-End

**Files:**
- Modify: `backend/tests/test_services/test_agent_service.py`

- [ ] **Step 1: Write end-to-end approval-resume test**

Add this test to `test_agent_service.py`:

```python
@pytest.mark.asyncio
async def test_approve_tool_call_resumes_execution_loop(monkeypatch, tmp_path):
    """Approval should resume the execution loop, not terminate the run."""
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, conversation_service, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=settings,
    )

    approval_id = "approval-resume-e2e"
    approval_event = asyncio.Event()

    from app.execution.models import LoopResult, LoopStatus
    from app.tools.base import BaseTool, ToolApprovalRequest, ToolResult

    class ResumeApprovalTool(BaseTool):
        @property
        def name(self) -> str:
            return "resume_approval_tool"

        @property
        def description(self) -> str:
            return "Tool that requires approval and then resumes"

        async def execute(self, args):
            if args.get("_approved_decision"):
                return ToolResult(success=True, output="approved and executed")

            return ToolResult(
                success=False,
                approval_required=True,
                approval=ToolApprovalRequest(
                    approval_id=approval_id,
                    tool_name="resume_approval_tool",
                    summary="需要审批后继续",
                    payload={"approved_decision": {"action": "allow", "command": "test", "execution_mode": "argv", "argv": ["echo"], "cwd": str(tmp_path), "timeout": 60, "reasons": [], "risks": [], "approval_kind": "argv_approval", "environment_snapshot": {"cwd": str(tmp_path)}}},
                ),
            )

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.event_callback = kwargs["event_callback"]
            self._approval_resume_event = asyncio.Event()
            self._approval_result = None

        def get_approval_resume_event(self):
            return self._approval_resume_event

        def set_approval_result(self, result):
            self._approval_result = result
            self._approval_resume_event.set()

        async def run(self, **kwargs):
            await self.event_callback("run:start", {"run_id": kwargs.get("run_id", "run-1")})
            await self.event_callback(
                "tool:start",
                {"tool_name": "resume_approval_tool", "arguments": {}, "tool_call_id": "call-1", "step_number": 1},
            )
            await self.event_callback(
                "approval:required",
                {
                    "approval_id": approval_id,
                    "tool_call_id": "call-1",
                    "tool_name": "resume_approval_tool",
                    "arguments": {},
                    "step_number": 1,
                    "approval": {
                        "approval_id": approval_id,
                        "tool_name": "resume_approval_tool",
                        "summary": "需要审批后继续",
                        "reasons": [],
                        "risks": [],
                        "payload": {},
                    },
                },
            )
            await self.event_callback(
                "run:waiting_for_approval",
                {"run_id": kwargs.get("run_id", "run-1"), "approval_id": approval_id},
            )

            await self._approval_resume_event.wait()

            if self._approval_result is not None:
                await self.event_callback("tool:result", {"tool_name": "resume_approval_tool", "tool_call_id": "call-1", "success": True, "output": "approved output", "error": None, "duration": 0.1})
                await self.event_callback("run:resuming", {"run_id": kwargs.get("run_id", "run-1"), "approval_id": approval_id})
                await self.event_callback("llm:content", {"content": "审批通过，继续执行"})
                await self.event_callback("run:complete", {})
                return LoopResult(id=kwargs.get("run_id", "run-1"), task=kwargs.get("task", ""), status=LoopStatus.COMPLETED, result="审批通过，继续执行")
            else:
                await self.event_callback("run:cancelled", {})
                return LoopResult(id=kwargs.get("run_id", "run-1"), task=kwargs.get("task", ""), status=LoopStatus.CANCELLED, result="审批被拒绝")

    class StubRuntimeAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def handle_event(self, event_type, data):
            return []

        def build_live_event(self, event_type, data):
            return None

        def get_live_state(self):
            return None

    captured_loops = []

    original_init = RapidExecutionLoop.__init__

    def capture_loop(**kwargs):
        loop = StubRapidExecutionLoop(**kwargs)
        captured_loops.append(loop)
        return loop

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", capture_loop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: object()
    )

    started = conversation_service.start_turn(
        session_id="session-1",
        content="运行需要审批的任务",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(tmp_path),
    )

    await asyncio.sleep(0.1)
    assert len(captured_loops) == 1
    stub_loop = captured_loops[0]

    pending = service.pending_approval_store.get(approval_id)
    assert pending is not None

    await service.approve_tool_call(
        session_id="session-1",
        run_id=started.run.id,
        approval_id=approval_id,
    )

    await asyncio.sleep(0.2)

    pending = service.pending_approval_store.get(approval_id)
    assert pending.status == "approved"

    run = conversation_service.run_repo.get(started.run.id)
    assert run.status == RunStatus.COMPLETED
```

- [ ] **Step 2: Update existing parametrized approval test**

The existing `test_tool_call_approval_decision_updates_trace_and_terminates_run` test currently expects `EventType.RUN_COMPLETED` for approve and `EventType.RUN_CANCELLED` for deny. Since there's no live loop in that test, the fallback path will still emit `RUN_COMPLETED`/`RUN_CANCELLED`, so the test should pass unchanged. But verify.

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_services/test_agent_service.py -v -k approval`

Expected: PASS

- [ ] **Step 3: Run the full test suite**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_services/test_agent_service.py tests/test_execution/test_rapid_loop.py tests/test_tools/test_shell_tool.py tests/test_security/test_command_policy.py -v`

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_services/test_agent_service.py
git commit -m "test: add end-to-end test for approval resuming execution loop"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ Loop suspends on approval instead of terminating — Task 1
- ✅ Loop resumes on approval with result injected — Task 1
- ✅ Loop cancels on denial — Task 1
- ✅ Runtime adapter handles `run:resuming` — Task 2
- ✅ AgentService wakes loop via `set_approval_result` — Task 3
- ✅ AgentService falls back when loop is dead — Task 3
- ✅ End-to-end test: approve resumes loop — Task 5
- ✅ End-to-end test: deny cancels loop — Task 4
- ⏳ Stale approval detection (if loop dies and user approves later) — handled by fallback path in Task 3

**2. Placeholder scan:**
- No TBD/TODO/FIXME found
- All code steps have complete implementations
- All test steps have complete test code

**3. Type consistency:**
- `set_approval_result(dict | None)` — used in Task 1 (loop reads it), Task 3 (agent writes it), Task 4 (tests)
- `get_approval_resume_event()` → `asyncio.Event` — used in Task 1 and Task 3
- `RapidExecutionLoop._approval_resume_event` and `_approval_result` — initialized in `__init__` (Task 1), read in `run()` (Task 1), written by `set_approval_result` (Task 1)
- `LoopStatus.RESUMING` — already exists in `models.py`, used in Task 1
- `EventType.RUN_RESUMING` — already exists in `conversation.py`, used in Task 2

**4. Cancel safety:**
- When `cancel_run` is called while loop is suspended on `await resume_event.wait()`, the `asyncio.CancelledError` propagates correctly — the `try/except CancelledError` block in `run()` handles it
- `expire_for_run` in `cancel_run` clears the pending approval store entry, preventing stale approvals
