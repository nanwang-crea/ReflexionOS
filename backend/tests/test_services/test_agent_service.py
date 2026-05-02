import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.agent_service as agent_service_module
from app.execution.models import LoopResult, LoopStatus
from app.memory.context_assembly import ContextAssemblyResult
from app.memory.continuation_builder import ContinuationArtifactBuilder
from app.models.conversation import (
    ConversationEvent,
    EventType,
    MessageType,
    RunStatus,
    StreamState,
    TurnStatus,
)
from app.models.llm_config import (
    LLMSettings,
    ProviderInstanceConfig,
    ProviderModelConfig,
    ProviderType,
)
from app.models.project import Project
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.services.llm_provider_service import LLMProviderService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


class DummyConfigManager:
    def __init__(self, settings: LLMSettings | None = None):
        self.settings = SimpleNamespace(llm=settings or LLMSettings())

    def update_llm(self, llm_settings: LLMSettings):
        self.settings.llm = llm_settings


def build_provider(
    provider_id: str,
    name: str,
    model_ids: list[str],
    provider_type: ProviderType = ProviderType.OPENAI_COMPATIBLE,
):
    models = [
        ProviderModelConfig(
            id=model_id,
            display_name=model_id.upper(),
            model_name=model_id,
            enabled=True,
        )
        for model_id in model_ids
    ]
    return ProviderInstanceConfig(
        id=provider_id,
        name=name,
        provider_type=provider_type,
        api_key="test-key",
        base_url="https://example.com/v1",
        models=models,
        default_model_id=models[0].id,
        enabled=True,
    )


def build_service(monkeypatch, settings: LLMSettings | None = None):
    dummy_config = DummyConfigManager(settings)
    provider_service = LLMProviderService(config_manager=dummy_config)
    return agent_service_module.AgentService(llm_provider_service=provider_service), dummy_config


def build_service_with_db(
    monkeypatch,
    tmp_path,
    *,
    project: Project | None = None,
    session: Session | None = None,
    settings: LLMSettings | None = None,
):
    db = Database(str(tmp_path / "agent-service.db"))
    dummy_config = DummyConfigManager(settings)

    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    if project is not None:
        project_repo.save(project)
    if session is not None:
        session_repo.create(session)

    conversation_service = ConversationService(db=db)
    provider_service = LLMProviderService(config_manager=dummy_config)
    service = agent_service_module.AgentService(
        project_repo=project_repo,
        session_repo=session_repo,
        conversation_service=conversation_service,
        llm_provider_service=provider_service,
    )
    return service, conversation_service, dummy_config


def append_waiting_for_approval(conversation_service, *, session_id, turn_id, run_id, approval_id):
    message_id = f"msg-waiting-{approval_id}"
    conversation_service.append_events(
        session_id,
        [
            ConversationEvent(
                id=f"evt-tool-{approval_id}",
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                message_id=message_id,
                event_type=EventType.MESSAGE_CREATED,
                payload_json={
                    "message_id": message_id,
                    "turn_id": turn_id,
                    "run_id": run_id,
                    "role": "assistant",
                    "message_type": "tool_trace",
                    "turn_message_index": conversation_service.message_repo.next_turn_message_index(
                        turn_id
                    ),
                    "display_mode": "default",
                    "content_text": "",
                    "payload_json": {
                        "tool_name": "shell",
                        "arguments": {"command": "pytest -q"},
                        "tool_call_id": "call-1",
                        "approval_id": approval_id,
                        "status": "waiting_for_approval",
                    },
                },
            ),
            ConversationEvent(
                id=f"evt-waiting-{approval_id}",
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                event_type=EventType.RUN_WAITING_FOR_APPROVAL,
                payload_json={"approval_id": approval_id},
            )
        ],
    )
    return message_id


@pytest.mark.asyncio
async def test_start_turn_creates_turn_run_and_tracks_running_task(monkeypatch, tmp_path):
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

    started_event = asyncio.Event()
    finish_event = asyncio.Event()

    async def fake_run_turn(**kwargs):
        started_event.set()
        await finish_event.wait()

    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    result = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="请检查仓库",
        provider_id="provider-a",
        model_id="model-a",
    )

    await asyncio.wait_for(started_event.wait(), timeout=0.5)
    assert result.turn.session_id == "session-1"
    assert result.run.session_id == "session-1"
    assert result.run.id in service.running_tasks

    snapshot = conversation_service.get_snapshot("session-1")
    assert [turn.id for turn in snapshot.turns] == [result.turn.id]
    assert [run.id for run in snapshot.runs] == [result.run.id]
    assert snapshot.session.active_turn_id == result.turn.id

    finish_event.set()
    await asyncio.wait_for(service.running_tasks[result.run.id], timeout=0.5)
    await asyncio.sleep(0)
    assert result.run.id not in service.running_tasks
    assert result.run.id not in getattr(service, "_runtime_adapters", {})


@pytest.mark.asyncio
async def test_start_turn_broadcasts_seed_events_through_injected_broadcaster(
    monkeypatch, tmp_path
):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    db = Database(str(tmp_path / "agent-service-broadcaster.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(project)
    session_repo.create(session)
    conversation_service = ConversationService(db=db)
    provider_service = LLMProviderService(config_manager=DummyConfigManager(settings))
    sent_events = []

    class RecordingBroadcaster:
        async def send_event(self, session_id, event_type, data):
            sent_events.append((session_id, event_type, data))

    service = agent_service_module.AgentService(
        project_repo=project_repo,
        session_repo=session_repo,
        conversation_service=conversation_service,
        llm_provider_service=provider_service,
        conversation_broadcaster=RecordingBroadcaster(),
    )
    monkeypatch.setattr(service, "schedule_turn", lambda **kwargs: None)

    await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="请检查仓库",
        provider_id="provider-a",
        model_id="model-a",
    )

    persisted_events = conversation_service.list_events_after("session-1", 0)
    assert [event_type for _, event_type, _ in sent_events] == [
        "conversation:event" for _ in persisted_events
    ]
    assert {session_id for session_id, _, _ in sent_events} == {"session-1"}
    assert [data["seq"] for _, _, data in sent_events] == [event.seq for event in persisted_events]


@pytest.mark.asyncio
async def test_start_turn_rejects_session_from_another_project(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-2", project_id="project-2", title="跨项目会话")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=settings,
    )

    with pytest.raises(ValueError, match="会话不属于当前项目"):
        await service.start_turn(
            project_id="project-1",
            session_id="session-2",
            content="inspect repo",
            provider_id="provider-a",
            model_id="model-a",
        )


@pytest.mark.asyncio
async def test_cancel_run_cancels_task_and_marks_run_cancelled(monkeypatch, tmp_path):
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

    started_event = asyncio.Event()
    cancelled_event = asyncio.Event()

    async def fake_run_turn(**kwargs):
        adapter = agent_service_module.ConversationRuntimeAdapter(
            conversation_service=service.conversation_service,
            session_id=kwargs["session_id"],
            turn_id=kwargs["turn_id"],
            run_id=kwargs["run_id"],
        )
        adapter.handle_event("run:start", {})
        adapter.handle_event("llm:content", {"content": "正在执行"})
        adapter.handle_event(
            "tool:start",
            {"tool_name": "shell", "arguments": {"cmd": "sleep 10"}, "step_number": 1},
        )
        started_event.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            adapter.handle_event("run:cancelled", {})
            cancelled_event.set()
            raise

    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="请检查仓库",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(started_event.wait(), timeout=0.5)
    cancelled = await service.cancel_run(started.run.id)

    await asyncio.wait_for(cancelled_event.wait(), timeout=0.5)
    await asyncio.sleep(0)
    assert started.run.id not in service.running_tasks
    assert cancelled.status == RunStatus.CANCELLED

    snapshot = conversation_service.get_snapshot("session-1")
    run = next(run for run in snapshot.runs if run.id == started.run.id)
    notice_messages = [
        message
        for message in snapshot.messages
        if message.message_type == MessageType.SYSTEM_NOTICE and message.run_id == started.run.id
    ]
    related_messages = [
        message
        for message in snapshot.messages
        if message.run_id == started.run.id
        and message.message_type in {MessageType.ASSISTANT_MESSAGE, MessageType.TOOL_TRACE}
    ]

    assert run.status == RunStatus.CANCELLED
    assert len(notice_messages) == 1
    assert notice_messages[0].content_text == "本次执行已取消"
    assert all(message.stream_state != StreamState.STREAMING for message in related_messages)
    assert all(message.stream_state != StreamState.IDLE for message in related_messages)


@pytest.mark.asyncio
async def test_cancel_run_expires_pending_approval_for_cancelled_waiting_run(
    monkeypatch, tmp_path
):
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
    started = conversation_service.start_turn(
        session_id="session-1",
        content="等待审批",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(tmp_path),
    )
    service.pending_approval_store.create(
        approval_id="approval-1",
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={"summary": "Run tests"},
    )
    append_waiting_for_approval(
        conversation_service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        approval_id="approval-1",
    )

    cancelled = await service.cancel_run(started.run.id)

    assert cancelled.status == RunStatus.CANCELLED
    pending = service.pending_approval_store.get("approval-1")
    assert pending is not None
    assert pending.status == "expired"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_status", "expected_event_type", "expected_run_status", "expected_turn_status"),
    [
        (
            "approve",
            "approved",
            EventType.APPROVAL_APPROVED,
            RunStatus.COMPLETED,
            TurnStatus.COMPLETED,
        ),
        (
            "deny",
            "denied",
            EventType.APPROVAL_DENIED,
            RunStatus.CANCELLED,
            TurnStatus.CANCELLED,
        ),
    ],
)
async def test_tool_call_approval_decision_updates_trace_and_terminates_run(
    monkeypatch,
    tmp_path,
    action,
    expected_status,
    expected_event_type,
    expected_run_status,
    expected_turn_status,
):
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
    started = conversation_service.start_turn(
        session_id="session-1",
        content="等待审批",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(tmp_path),
    )
    service.pending_approval_store.create(
        approval_id="approval-1",
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={"summary": "Run tests"},
    )
    message_id = append_waiting_for_approval(
        conversation_service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        approval_id="approval-1",
    )

    if action == "approve":
        await service.approve_tool_call(
            session_id="session-1",
            run_id=started.run.id,
            approval_id="approval-1",
        )
    else:
        await service.deny_tool_call(
            session_id="session-1",
            run_id=started.run.id,
            approval_id="approval-1",
        )

    events = conversation_service.list_events_after("session-1", 0)
    tail_event_types = [event.event_type for event in events[-3:]]
    assert tail_event_types == [
        EventType.MESSAGE_PAYLOAD_UPDATED,
        expected_event_type,
        EventType.RUN_COMPLETED if action == "approve" else EventType.RUN_CANCELLED,
    ]
    assert EventType.RUN_RESUMING not in tail_event_types

    trace = conversation_service.message_repo.get(message_id)
    run = conversation_service.run_repo.get(started.run.id)
    turn = conversation_service.turn_repo.get(started.turn.id)
    snapshot = conversation_service.get_snapshot("session-1")
    pending = service.pending_approval_store.get("approval-1")

    assert trace is not None
    assert trace.payload_json["status"] == expected_status
    assert trace.payload_json["approval_id"] == "approval-1"
    assert run is not None
    assert run.status == expected_run_status
    assert run.finished_at is not None
    assert turn is not None
    assert turn.status == expected_turn_status
    assert turn.active_run_id is None
    assert snapshot.session.active_turn_id is None
    assert pending is not None
    assert pending.status == expected_status


@pytest.mark.asyncio
async def test_approve_tool_call_does_not_revive_run_cancelled_before_append(
    monkeypatch, tmp_path
):
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
    started = conversation_service.start_turn(
        session_id="session-1",
        content="等待审批",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(tmp_path),
    )
    service.pending_approval_store.create(
        approval_id="approval-1",
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        step_number=1,
        tool_call_id="call-1",
        tool_name="shell",
        tool_arguments={"command": "pytest -q"},
        approval_payload={"summary": "Run tests"},
    )
    append_waiting_for_approval(
        conversation_service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        approval_id="approval-1",
    )
    before_seq = conversation_service.get_snapshot("session-1").session.last_event_seq
    approval_append_attempted = threading.Event()
    original_acquire_session_write_lock = conversation_service._acquire_session_write_lock
    original_append_events = conversation_service.append_events
    approval_errors: list[Exception] = []

    def signal_approval_append(session_id, events):
        if events and events[0].event_type == EventType.APPROVAL_APPROVED:
            approval_append_attempted.set()
        return original_append_events(session_id, events)

    def approve_tool_call_in_thread():
        try:
            asyncio.run(
                service.approve_tool_call(
                    session_id="session-1",
                    run_id=started.run.id,
                    approval_id="approval-1",
                )
            )
        except Exception as exc:
            approval_errors.append(exc)

    monkeypatch.setattr(conversation_service, "append_events", signal_approval_append)

    with original_acquire_session_write_lock("session-1"):
        approval_thread = threading.Thread(target=approve_tool_call_in_thread)
        approval_thread.start()
        approval_append_attempted.wait(timeout=0.2)
        conversation_service.cancel_run(started.run.id)
        service.pending_approval_store.expire_for_run(started.run.id)

    approval_thread.join(timeout=1)
    assert not approval_thread.is_alive()
    assert len(approval_errors) == 1
    assert isinstance(approval_errors[0], ValueError)
    assert "运行未在等待审批" in str(approval_errors[0])

    with pytest.raises(ValueError, match="运行未在等待审批"):
        await service.approve_tool_call(
            session_id="session-1",
            run_id=started.run.id,
            approval_id="approval-1",
        )

    run = conversation_service.run_repo.get(started.run.id)
    assert run is not None
    assert run.status == RunStatus.CANCELLED
    pending = service.pending_approval_store.get("approval-1")
    assert pending is not None
    assert pending.status == "expired"
    events = conversation_service.list_events_after("session-1", before_seq)
    assert EventType.APPROVAL_APPROVED not in [event.event_type for event in events]
    assert EventType.RUN_RESUMING not in [event.event_type for event in events]


@pytest.mark.asyncio
async def test_run_turn_broadcasts_live_chunks_and_only_persists_terminal_events(
    monkeypatch, tmp_path
):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=settings,
    )

    call_order = []

    class StubPersistedEvent:
        def model_dump(self, mode="python"):
            assert mode == "json"
            return {"id": "evt-1", "seq": 7, "event_type": "message.content_committed"}

    class StubRuntimeAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def handle_event(self, event_type, data):
            call_order.append(("persist", event_type))
            if event_type == "llm:content":
                return []
            return [StubPersistedEvent()]

        def build_live_event(self, event_type, data):
            if event_type != "llm:content":
                return None
            return {
                "session_id": "session-1",
                "run_id": "run-1",
                "turn_id": "turn-1",
                "message_id": "msg-1",
                "content_text": data["content"],
                "delta": data["content"],
                "stream_state": "streaming",
            }

        def get_live_state(self):
            return {
                "session_id": "session-1",
                "run_id": "run-1",
                "turn_id": "turn-1",
                "message_id": "msg-1",
                "content_text": "hello",
                "stream_state": "streaming",
            }

    class StubBroadcaster:
        async def send_event(self, session_id, event_type, data):
            identifier = data.get("id") or data.get("message_id")
            call_order.append(("broadcast", event_type, identifier))

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.event_callback = kwargs["event_callback"]

        async def run(self, **kwargs):
            await self.event_callback("llm:content", {"content": "hello"})
            await self.event_callback("run:complete", {})
            return LoopResult(id=kwargs["run_id"], task=kwargs["task"], status=LoopStatus.COMPLETED)

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: object()
    )
    service.conversation_broadcaster = StubBroadcaster()

    await service._run_turn(
        run_id="run-1",
        session_id="session-1",
        turn_id="turn-1",
        task="hello",
        project_id="project-1",
        project_path=str(tmp_path),
        provider_id="provider-a",
        model_id="model-a",
    )

    assert call_order[0] == ("persist", "llm:content")
    assert call_order[1] == ("broadcast", "conversation:live_event", "msg-1")
    assert call_order[2] == ("persist", "run:complete")
    assert call_order[3] == ("broadcast", "conversation:event", "evt-1")
    assert service.get_live_state("session-1") is None


@pytest.mark.asyncio
async def test_run_turn_registers_pending_approval_from_runtime_event(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=settings,
    )

    class StubRuntimeAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def handle_event(self, event_type, data):
            return []

        def build_live_event(self, event_type, data):
            return None

        def get_live_state(self):
            return None

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.event_callback = kwargs["event_callback"]

        async def run(self, **kwargs):
            await self.event_callback(
                "approval:required",
                {
                    "approval_id": "approval-runtime",
                    "tool_call_id": "call-runtime",
                    "tool_name": "shell",
                    "arguments": {"command": "pytest -q"},
                    "step_number": 2,
                    "approval": {"summary": "Run tests"},
                },
            )
            return LoopResult(
                id=kwargs["run_id"],
                task=kwargs["task"],
                status=LoopStatus.WAITING_FOR_APPROVAL,
            )

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: object()
    )

    await service._run_turn(
        run_id="run-1",
        session_id="session-1",
        turn_id="turn-1",
        task="hello",
        project_id="project-1",
        project_path=str(tmp_path),
        provider_id="provider-a",
        model_id="model-a",
    )

    pending = service.pending_approval_store.get("approval-runtime")
    assert pending is not None
    assert pending.session_id == "session-1"
    assert pending.turn_id == "turn-1"
    assert pending.run_id == "run-1"
    assert pending.step_number == 2
    assert pending.tool_call_id == "call-runtime"
    assert pending.tool_name == "shell"
    assert pending.tool_arguments == {"command": "pytest -q"}
    assert pending.approval_payload == {"summary": "Run tests"}


@pytest.mark.asyncio
async def test_run_turn_builds_isolated_tool_registry_per_run(monkeypatch, tmp_path):
    project_root = tmp_path / "project-root"
    project_root.mkdir()
    other_project_root = tmp_path / "other-project-root"
    other_project_root.mkdir()

    project = Project(id="project-1", name="ReflexionOS", path=str(project_root))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=settings,
    )

    captured_registries = []

    class StubRuntimeAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def handle_event(self, event_type, data):
            return []

        def build_live_event(self, event_type, data):
            return None

        def get_live_state(self):
            return None

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            captured_registries.append(kwargs["tool_registry"])

        async def run(self, **kwargs):
            return LoopResult(id=kwargs["run_id"], task=kwargs["task"], status=LoopStatus.COMPLETED)

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: object()
    )

    await service._run_turn(
        run_id="run-1",
        session_id="session-1",
        turn_id="turn-1",
        task="hello",
        project_id="project-1",
        project_path=str(project_root),
        provider_id="provider-a",
        model_id="model-a",
    )
    await service._run_turn(
        run_id="run-2",
        session_id="session-1",
        turn_id="turn-1",
        task="hello again",
        project_id="project-1",
        project_path=str(other_project_root),
        provider_id="provider-a",
        model_id="model-a",
    )

    assert len(captured_registries) == 2
    assert captured_registries[0] is not captured_registries[1]

    first_file_security = captured_registries[0].tools["file"].security
    second_file_security = captured_registries[1].tools["file"].security
    first_project_path = str(Path(project_root).resolve())
    second_project_path = str(Path(other_project_root).resolve())

    assert first_file_security.base_dir == first_project_path
    assert second_file_security.base_dir == second_project_path
    assert first_project_path in first_file_security.allowed_base_paths
    assert second_project_path in second_file_security.allowed_base_paths


@pytest.mark.asyncio
async def test_run_tool_registry_includes_memory_tool(monkeypatch, tmp_path):
    project_root = tmp_path / "project-root"
    project_root.mkdir()

    project = Project(id="project-1", name="ReflexionOS", path=str(project_root))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=settings,
    )

    captured_registries = []

    class StubRuntimeAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def handle_event(self, event_type, data):
            return []

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            captured_registries.append(kwargs["tool_registry"])

        async def run(self, **kwargs):
            return LoopResult(id=kwargs["run_id"], task=kwargs["task"], status=LoopStatus.COMPLETED)

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: object()
    )

    await service._run_turn(
        run_id="run-1",
        session_id="session-1",
        turn_id="turn-1",
        task="hello",
        project_id="project-1",
        project_path=str(project_root),
        provider_id="provider-a",
        model_id="model-a",
    )

    assert len(captured_registries) == 1
    assert "memory" in captured_registries[0].list_tools()

    run_tool_names = {
        definition.name for definition in captured_registries[0].get_tool_definitions()
    }
    assert "memory" in run_tool_names


@pytest.mark.asyncio
async def test_run_turn_passes_context_assembly_into_execution_loop(monkeypatch, tmp_path):
    project_root = tmp_path / "project-root"
    project_root.mkdir()

    project = Project(id="project-1", name="ReflexionOS", path=str(project_root))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=settings,
    )

    captured = {}

    class StubRuntimeAdapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def handle_event(self, event_type, data):
            return []

        def build_live_event(self, event_type, data):
            return None

        def get_live_state(self):
            return None

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.event_callback = kwargs["event_callback"]

        async def run(self, **kwargs):
            captured.update(kwargs)
            await self.event_callback("run:complete", {})
            return LoopResult(id=kwargs["run_id"], task=kwargs["task"], status=LoopStatus.COMPLETED)

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: object()
    )
    monkeypatch.setattr(service, "_generate_and_persist_continuation_artifact", AsyncMock())

    service.context_assembler.build_for_session = lambda **_: ContextAssemblyResult(
        system_sections=["STATIC"],
        recent_messages=[{"role": "user", "content": "seeded"}],
        supplemental_block="handoff",
    )

    await service._run_turn(
        run_id="run-1",
        session_id="session-1",
        turn_id="turn-1",
        task="hello",
        project_id="project-1",
        project_path=str(project_root),
        provider_id="provider-a",
        model_id="model-a",
    )

    assert captured["seed_messages"] == [{"role": "user", "content": "seeded"}]
    assert captured["supplemental_context"] == "handoff"
    assert captured["system_sections"] == ["STATIC"]


@pytest.mark.asyncio
async def test_run_turn_persists_llm_generated_continuation_artifact(monkeypatch, tmp_path):
    project_root = tmp_path / "project-root"
    project_root.mkdir()

    project = Project(id="project-1", name="ReflexionOS", path=str(project_root))
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

    started = conversation_service.start_turn(
        session_id="session-1",
        content="请继续实现 context assembly",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(project_root),
    )

    class StubBroadcaster:
        async def send_event(self, session_id, event_type, data):
            return None

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.event_callback = kwargs["event_callback"]

        async def run(self, **kwargs):
            await self.event_callback("run:complete", {})
            return LoopResult(id=kwargs["run_id"], task=kwargs["task"], status=LoopStatus.COMPLETED)

    class StubLLM:
        async def complete(self, messages, tools=None):
            return SimpleNamespace(
                content="当前目标: 继续实现\n已确认事实: a\n未解决点: b\n下一步建议: c"
            )

    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: StubLLM()
    )
    service.conversation_broadcaster = StubBroadcaster()

    await service._run_turn(
        run_id=started.run.id,
        session_id="session-1",
        turn_id=started.turn.id,
        task="请继续实现 context assembly",
        project_id="project-1",
        project_path=str(project_root),
        provider_id="provider-a",
        model_id="model-a",
    )

    snapshot = conversation_service.get_snapshot("session-1")
    continuation = [
        message
        for message in snapshot.messages
        if message.turn_id == started.turn.id
        and message.message_type == MessageType.SYSTEM_NOTICE
        and isinstance(message.payload_json, dict)
        and message.payload_json.get("kind") == "continuation_artifact"
    ]
    assert len(continuation) == 1
    assert continuation[0].display_mode == "collapsed"
    assert continuation[0].payload_json["exclude_from_recall"] is True
    assert continuation[0].payload_json["exclude_from_memory_promotion"] is True
    assert "当前目标" in continuation[0].content_text


@pytest.mark.asyncio
async def test_run_turn_skips_continuation_after_cancelled_execution(monkeypatch, tmp_path):
    project_root = tmp_path / "project-root"
    project_root.mkdir()

    project = Project(id="project-1", name="ReflexionOS", path=str(project_root))
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

    started = conversation_service.start_turn(
        session_id="session-1",
        content="请检查远程状态",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(project_root),
    )

    class StubBroadcaster:
        async def send_event(self, session_id, event_type, data):
            return None

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            pass

        async def run(self, **kwargs):
            return LoopResult(
                id=kwargs["run_id"],
                task=kwargs["task"],
                status=LoopStatus.CANCELLED,
                result="执行已取消：LLM 重试次数已达上限",
            )

    class StubLLM:
        async def complete(self, messages, tools=None):
            return SimpleNamespace(content="不应该生成")

    continuation_mock = AsyncMock()

    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(
        agent_service_module.LLMAdapterFactory, "create", lambda *args, **kwargs: StubLLM()
    )
    monkeypatch.setattr(service, "_generate_and_persist_continuation_artifact", continuation_mock)
    service.conversation_broadcaster = StubBroadcaster()

    await service._run_turn(
        run_id=started.run.id,
        session_id="session-1",
        turn_id=started.turn.id,
        task="请检查远程状态",
        project_id="project-1",
        project_path=str(project_root),
        provider_id="provider-a",
        model_id="model-a",
    )

    continuation_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_continuation_generation_sends_budgeted_transcript_to_llm(monkeypatch, tmp_path):
    project_root = tmp_path / "project-root"
    project_root.mkdir()

    project = Project(id="project-1", name="ReflexionOS", path=str(project_root))
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
    service.continuation_builder = ContinuationArtifactBuilder(
        max_transcript_chars=1_500,
        max_item_chars=800,
        max_tool_output_chars=400,
        tool_output_head_chars=120,
        tool_output_tail_chars=120,
    )

    started = conversation_service.start_turn(
        session_id="session-1",
        content="请继续实现 context assembly",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(project_root),
    )
    adapter = agent_service_module.ConversationRuntimeAdapter(
        conversation_service=conversation_service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )
    adapter.handle_event(
        "tool:start",
        {"tool_name": "shell", "arguments": {"command": "pytest -q"}, "step_number": 1},
    )
    huge_output = (
        "BEGIN-"
        + ("head-block-" * 30)
        + ("huge-middle-" * 5_000)
        + ("tail-block-" * 30)
        + "-TAIL-END"
    )
    adapter.handle_event(
        "tool:result",
        {
            "tool_name": "shell",
            "step_number": 1,
            "success": False,
            "output": huge_output,
            "error": None,
            "duration": 0.1,
        },
    )

    captured_messages = []

    class StubLLM:
        async def complete(self, messages, tools=None):
            nonlocal captured_messages
            captured_messages = messages
            return SimpleNamespace(
                content="当前目标: 继续实现\n已确认事实: a\n未解决点: b\n下一步建议: c"
            )

    await service._generate_and_persist_continuation_artifact(
        llm=StubLLM(),
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        task="请继续实现 context assembly",
    )

    assert [message.role for message in captured_messages] == ["system", "user"]
    captured_input = captured_messages[1].content
    assert len(captured_input) < 3_000
    assert "Task (current user input):" in captured_input
    assert "Transcript (oldest to newest, may include tool traces):" in captured_input
    assert "BEGIN-" in captured_input
    assert "-TAIL-END" in captured_input
    assert "省略" in captured_input
    assert "huge-middle-huge-middle-huge-middle" not in captured_input


@pytest.mark.asyncio
async def test_cancel_run_fallback_adapter_closes_existing_open_messages(monkeypatch, tmp_path):
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

    run_ready = asyncio.Event()

    async def fake_run_turn(**kwargs):
        adapter = agent_service_module.ConversationRuntimeAdapter(
            conversation_service=conversation_service,
            session_id=kwargs["session_id"],
            turn_id=kwargs["turn_id"],
            run_id=kwargs["run_id"],
        )
        adapter.handle_event("run:start", {})
        adapter.handle_event("llm:content", {"content": "streaming assistant"})
        adapter.handle_event(
            "tool:start",
            {"tool_name": "shell", "arguments": {"cmd": "sleep 1"}, "step_number": 1},
        )
        run_ready.set()

    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="请检查仓库",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(run_ready.wait(), timeout=0.5)
    await asyncio.sleep(0)
    assert started.run.id not in service.running_tasks

    cancelled = await service.cancel_run(started.run.id)
    assert cancelled.status == RunStatus.CANCELLED

    snapshot = conversation_service.get_snapshot("session-1")
    related_messages = [
        message
        for message in snapshot.messages
        if message.run_id == started.run.id
        and message.message_type in {MessageType.ASSISTANT_MESSAGE, MessageType.TOOL_TRACE}
    ]
    notices = [
        message
        for message in snapshot.messages
        if message.run_id == started.run.id and message.message_type == MessageType.SYSTEM_NOTICE
    ]

    assert len(notices) == 1
    assert all(
        message.stream_state not in {StreamState.IDLE, StreamState.STREAMING}
        for message in related_messages
    )


@pytest.mark.asyncio
async def test_approve_tool_call_executes_stored_shell_command_and_resumes_run(
    monkeypatch, tmp_path
):
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
    started = conversation_service.start_turn(
        session_id="session-1",
        content="运行测试",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(tmp_path),
    )
    approved_decision = {
        "action": "allow",
        "execution_mode": "argv",
        "command": "echo hello",
        "argv": ["echo", "hello"],
        "cwd": str(tmp_path),
        "timeout": 60,
        "reasons": [],
        "risks": [],
        "approval_kind": "argv_approval",
        "environment_snapshot": {"cwd": str(tmp_path)},
    }
    service.pending_approval_store.create(
        approval_id="approval-resume",
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        step_number=1,
        tool_call_id="call-resume",
        tool_name="shell",
        tool_arguments={"command": "echo hello"},
        approval_payload={
            "summary": "运行 echo hello",
            "approved_decision": approved_decision,
        },
    )
    message_id = append_waiting_for_approval(
        conversation_service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        approval_id="approval-resume",
    )

    await service.approve_tool_call(
        session_id="session-1",
        run_id=started.run.id,
        approval_id="approval-resume",
    )

    events = conversation_service.list_events_after("session-1", 0)
    event_types = [event.event_type for event in events]

    assert EventType.APPROVAL_APPROVED in event_types
    pending = service.pending_approval_store.get("approval-resume")
    assert pending.status == "approved"

    run = conversation_service.run_repo.get(started.run.id)
    assert run.status == RunStatus.COMPLETED

    trace = conversation_service.message_repo.get(message_id)
    assert trace.payload_json["status"] == "approved"


@pytest.mark.asyncio
async def test_deny_tool_call_does_not_execute_command(monkeypatch, tmp_path):
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
    started = conversation_service.start_turn(
        session_id="session-1",
        content="运行测试",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(tmp_path),
    )
    service.pending_approval_store.create(
        approval_id="approval-deny",
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        step_number=1,
        tool_call_id="call-deny",
        tool_name="shell",
        tool_arguments={"command": "rm -rf .pytest_cache"},
        approval_payload={"summary": "删除缓存"},
    )
    message_id = append_waiting_for_approval(
        conversation_service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        approval_id="approval-deny",
    )

    await service.deny_tool_call(
        session_id="session-1",
        run_id=started.run.id,
        approval_id="approval-deny",
    )

    pending = service.pending_approval_store.get("approval-deny")
    assert pending.status == "denied"

    trace = conversation_service.message_repo.get(message_id)
    assert trace.payload_json["status"] == "denied"

    run = conversation_service.run_repo.get(started.run.id)
    assert run.status == RunStatus.CANCELLED
