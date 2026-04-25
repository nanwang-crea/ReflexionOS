import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.agent_service as agent_service_module
from app.models.conversation import MessageType, RunStatus, StreamState
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
        adapter.handle_event("execution:start", {})
        adapter.handle_event("llm:content", {"content": "正在执行"})
        adapter.handle_event(
            "tool:start",
            {"tool_name": "shell", "arguments": {"cmd": "sleep 10"}, "step_number": 1},
        )
        started_event.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            adapter.handle_event("execution:cancelled", {})
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
        message for message in snapshot.messages
        if message.message_type == MessageType.SYSTEM_NOTICE and message.run_id == started.run.id
    ]
    related_messages = [
        message for message in snapshot.messages
        if message.run_id == started.run.id
        and message.message_type in {MessageType.ASSISTANT_MESSAGE, MessageType.TOOL_TRACE}
    ]

    assert run.status == RunStatus.CANCELLED
    assert len(notice_messages) == 1
    assert notice_messages[0].content_text == "本次执行已取消"
    assert all(message.stream_state != StreamState.STREAMING for message in related_messages)
    assert all(message.stream_state != StreamState.IDLE for message in related_messages)


@pytest.mark.asyncio
async def test_run_turn_broadcasts_live_chunks_and_only_persists_terminal_events(monkeypatch, tmp_path):
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

    class StubWsManager:
        async def send_event(self, session_id, event_type, data):
            identifier = data.get("id") or data.get("message_id")
            call_order.append(("broadcast", event_type, identifier))

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.event_callback = kwargs["event_callback"]

        async def run(self, **kwargs):
            await self.event_callback("llm:content", {"content": "hello"})
            await self.event_callback("execution:complete", {})

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "ws_manager", StubWsManager())
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(agent_service_module.LLMAdapterFactory, "create", lambda _: object())

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
    assert call_order[1] == ("broadcast", "conversation.live_event", "msg-1")
    assert call_order[2] == ("persist", "execution:complete")
    assert call_order[3] == ("broadcast", "conversation.event", "evt-1")
    assert service.get_live_state("session-1") is None


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

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            captured_registries.append(kwargs["tool_registry"])

        async def run(self, **kwargs):
            return None

    monkeypatch.setattr(agent_service_module, "ConversationRuntimeAdapter", StubRuntimeAdapter)
    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)
    monkeypatch.setattr(agent_service_module.LLMAdapterFactory, "create", lambda _: object())

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

    shared_file_security = service.tool_registry.tools["file"].security
    assert shared_file_security.base_dir == str(Path.cwd().resolve())
    assert first_project_path not in shared_file_security.allowed_base_paths
    assert second_project_path not in shared_file_security.allowed_base_paths


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
        adapter.handle_event("execution:start", {})
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
        message for message in snapshot.messages
        if message.run_id == started.run.id
        and message.message_type in {MessageType.ASSISTANT_MESSAGE, MessageType.TOOL_TRACE}
    ]
    notices = [
        message for message in snapshot.messages
        if message.run_id == started.run.id and message.message_type == MessageType.SYSTEM_NOTICE
    ]

    assert len(notices) == 1
    assert all(message.stream_state not in {StreamState.IDLE, StreamState.STREAMING} for message in related_messages)
