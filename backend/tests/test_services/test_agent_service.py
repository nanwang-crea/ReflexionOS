import asyncio
import contextlib
from datetime import datetime
from types import SimpleNamespace

import pytest

import app.services.agent_service as agent_service_module
from app.models.execution import ExecutionCreate
from app.models.llm_config import (
    LLMSettings,
    ProviderInstanceConfig,
    ProviderModelConfig,
    ProviderType,
)
from app.models.project import Project
from app.models.session import Session
from app.models.transcript import TranscriptRecord
from app.services.transcript_service import TranscriptService


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
    monkeypatch.setattr(agent_service_module, "config_manager", dummy_config)
    return agent_service_module.AgentService(), dummy_config


class StubProjectRepo:
    def __init__(self, project: Project | None):
        self.project = project

    def get(self, project_id: str):
        if self.project is None:
            return None
        assert project_id == self.project.id
        return self.project


class StubSessionRepo:
    def __init__(self, session: Session | None):
        self.session = session

    def get(self, session_id: str):
        if self.session is None:
            return None
        assert session_id == self.session.id
        return self.session


class RecordingConversationRepo:
    def __init__(self):
        self.saved_messages = []

    def save_messages(self, messages):
        self.saved_messages.extend(messages)


def build_service_with_repos(
    monkeypatch,
    *,
    project: Project | None = None,
    session: Session | None = None,
    settings: LLMSettings | None = None,
):
    dummy_config = DummyConfigManager(settings)
    monkeypatch.setattr(agent_service_module, "config_manager", dummy_config)
    service = agent_service_module.AgentService(
        project_repo=StubProjectRepo(project),
        session_repo=StubSessionRepo(session),
    )
    return service, dummy_config


def test_create_provider_initializes_default_selection(monkeypatch):
    service, dummy_config = build_service(monkeypatch)
    provider = build_provider("provider-openai", "OpenAI 官方", ["gpt-4.1", "gpt-4.1-mini"])

    saved_provider = service.create_provider(provider)
    selection = service.get_default_selection()

    assert saved_provider.id == "provider-openai"
    assert selection.configured is True
    assert selection.provider_id == "provider-openai"
    assert selection.model_id == "gpt-4.1"
    assert dummy_config.settings.llm.default_provider_id == "provider-openai"
    assert dummy_config.settings.llm.default_model_id == "gpt-4.1"


def test_resolve_llm_config_uses_explicit_provider_and_model(monkeypatch):
    provider_a = build_provider("provider-a", "Provider A", ["model-a"])
    provider_b = build_provider("provider-b", "Provider B", ["model-b", "model-c"])
    settings = LLMSettings(
        providers=[provider_a, provider_b],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service(monkeypatch, settings)

    resolved = service.resolve_llm_config("provider-b", "model-c")

    assert resolved.provider_id == "provider-b"
    assert resolved.model_id == "model-c"
    assert resolved.model == "model-c"
    assert resolved.provider_type == ProviderType.OPENAI_COMPATIBLE


def test_resolve_llm_config_rejects_unknown_explicit_model(monkeypatch):
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service(monkeypatch, settings)

    with pytest.raises(ValueError, match="所选模型不存在或已禁用"):
        service.resolve_llm_config("provider-a", "missing-model")


@pytest.mark.asyncio
async def test_create_execution_creates_execution_for_session_in_same_project(
    monkeypatch,
    tmp_path,
):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    service, _ = build_service_with_repos(monkeypatch, project=project, session=session)

    execution = await service.create_execution(
        ExecutionCreate(
            project_id="project-1",
            session_id="session-1",
            task="inspect repo",
        )
    )

    assert execution.project_id == "project-1"
    assert execution.session_id == "session-1"
    assert execution.task == "inspect repo"


@pytest.mark.asyncio
async def test_create_execution_rejects_missing_session(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    service, _ = build_service_with_repos(monkeypatch, project=project, session=None)

    with pytest.raises(ValueError, match="会话不存在"):
        await service.create_execution(
            ExecutionCreate(
                project_id="project-1",
                session_id="missing-session",
                task="inspect repo",
            )
        )


@pytest.mark.asyncio
async def test_create_execution_rejects_session_from_another_project(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-2", project_id="project-2", title="跨项目会话")
    service, _ = build_service_with_repos(monkeypatch, project=project, session=session)

    with pytest.raises(ValueError, match="会话不属于当前项目"):
        await service.create_execution(
            ExecutionCreate(
                project_id="project-1",
                session_id="session-2",
                task="inspect repo",
            )
        )


@pytest.mark.asyncio
async def test_create_execution_prioritizes_missing_project_before_session_validation(monkeypatch):
    class SessionRepoThatMustNotBeCalled:
        def get(self, session_id: str):
            raise AssertionError("session lookup should not happen when project is missing")

    dummy_config = DummyConfigManager()
    monkeypatch.setattr(agent_service_module, "config_manager", dummy_config)
    service = agent_service_module.AgentService(
        project_repo=StubProjectRepo(None),
        session_repo=SessionRepoThatMustNotBeCalled(),
    )

    with pytest.raises(ValueError, match="项目不存在"):
        await service.create_execution(
            ExecutionCreate(
                project_id="missing-project",
                session_id="session-2",
                task="inspect repo",
            )
        )


def test_build_session_history_groups_items_into_rounds():
    class StubSessionRepo:
        def get(self, session_id: str):
            assert session_id == "session-1"
            return SimpleNamespace(id="session-1", project_id="project-1")

    class StubConversationRepo:
        def list_by_session(self, session_id: str):
            assert session_id == "session-1"
            return [
                TranscriptRecord(
                    id="msg-1",
                    execution_id="exec-1",
                    session_id="session-1",
                    project_id="project-1",
                    item_type="user-message",
                    content="请总结今天进展",
                    receipt_status=None,
                    details_json=[],
                    sequence=0,
                    created_at=datetime(2026, 4, 20, 12, 0, 0),
                ),
                TranscriptRecord(
                    id="msg-2",
                    execution_id="exec-1",
                    session_id="session-1",
                    project_id="project-1",
                    item_type="assistant-message",
                    content="已完成 Task 1 和 Task 2",
                    receipt_status=None,
                    details_json=[],
                    sequence=1,
                    created_at=datetime(2026, 4, 20, 12, 0, 1),
                ),
            ]

    service = TranscriptService(
        conversation_repo=StubConversationRepo(),
        session_repo=StubSessionRepo(),
    )

    history = service.build_session_history("session-1")

    assert history.session_id == "session-1"
    assert history.project_id == "project-1"
    assert len(history.rounds) == 1
    assert history.rounds[0].id == "round-msg-1"
    assert [item.type for item in history.rounds[0].items] == ["user-message", "assistant-message"]


def test_build_session_history_uses_session_resource_when_transcript_is_empty():
    class StubSessionRepo:
        def get(self, session_id: str):
            assert session_id == "session-empty"
            return SimpleNamespace(id="session-empty", project_id="project-1")

    class StubConversationRepo:
        def list_by_session(self, session_id: str):
            assert session_id == "session-empty"
            return []

    service = TranscriptService(
        conversation_repo=StubConversationRepo(),
        session_repo=StubSessionRepo(),
    )

    history = service.build_session_history("session-empty")

    assert history.session_id == "session-empty"
    assert history.project_id == "project-1"
    assert history.rounds == []


def test_build_session_history_rejects_missing_session():
    class StubSessionRepo:
        def get(self, session_id: str):
            assert session_id == "missing-session"
            return None

    class StubConversationRepo:
        def list_by_session(self, session_id: str):
            raise AssertionError("conversation rows should not be read for missing sessions")

    service = TranscriptService(
        conversation_repo=StubConversationRepo(),
        session_repo=StubSessionRepo(),
    )

    with pytest.raises(ValueError, match="会话不存在"):
        service.build_session_history("missing-session")


@pytest.mark.asyncio
async def test_run_execution_skips_persisting_cancelled_transcript(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service_with_repos(
        monkeypatch,
        project=project,
        session=session,
        settings=settings,
    )
    conversation_repo = RecordingConversationRepo()
    service.conversation_repo = conversation_repo

    execution = await service.create_execution(
        ExecutionCreate(
            project_id="project-1",
            session_id="session-1",
            task="cancel me",
        )
    )

    monkeypatch.setattr(agent_service_module.LLMAdapterFactory, "create", lambda _: object())

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, **kwargs):
            return execution.model_copy(update={
                "status": agent_service_module.ExecutionStatus.CANCELLED,
                "result": "执行已取消",
                "transcript_items": [],
                "completed_at": datetime.now(),
            })

    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)

    result = await service.run_execution(execution.id)

    assert result.status == agent_service_module.ExecutionStatus.CANCELLED
    assert conversation_repo.saved_messages == []


@pytest.mark.asyncio
async def test_run_execution_persists_failed_transcript(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service_with_repos(
        monkeypatch,
        project=project,
        session=session,
        settings=settings,
    )
    conversation_repo = RecordingConversationRepo()
    service.conversation_repo = conversation_repo

    execution = await service.create_execution(
        ExecutionCreate(
            project_id="project-1",
            session_id="session-1",
            task="fail me",
        )
    )

    failed_transcript = [
        {
            "id": f"conv-{execution.id}-0",
            "execution_id": execution.id,
            "session_id": execution.session_id,
            "project_id": execution.project_id,
            "item_type": "user-message",
            "content": "fail me",
            "receipt_status": None,
            "details_json": [],
            "sequence": 0,
            "created_at": datetime.now(),
        },
        {
            "id": f"conv-{execution.id}-1",
            "execution_id": execution.id,
            "session_id": execution.session_id,
            "project_id": execution.project_id,
            "item_type": "assistant-message",
            "content": "执行异常: boom",
            "receipt_status": None,
            "details_json": [],
            "sequence": 1,
            "created_at": datetime.now(),
        },
    ]

    monkeypatch.setattr(agent_service_module.LLMAdapterFactory, "create", lambda _: object())

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, **kwargs):
            return execution.model_copy(update={
                "status": agent_service_module.ExecutionStatus.FAILED,
                "result": "执行异常: boom",
                "transcript_items": failed_transcript,
                "completed_at": datetime.now(),
            })

    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)

    result = await service.run_execution(execution.id)

    assert result.status == agent_service_module.ExecutionStatus.FAILED
    assert [message.content for message in conversation_repo.saved_messages] == [
        "fail me",
        "执行异常: boom",
    ]


@pytest.mark.asyncio
async def test_run_execution_persists_completed_transcript(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service_with_repos(
        monkeypatch,
        project=project,
        session=session,
        settings=settings,
    )
    conversation_repo = RecordingConversationRepo()
    service.conversation_repo = conversation_repo

    execution = await service.create_execution(
        ExecutionCreate(
            project_id="project-1",
            session_id="session-1",
            task="complete me",
        )
    )

    completed_transcript = [
        {
            "id": f"conv-{execution.id}-0",
            "execution_id": execution.id,
            "session_id": execution.session_id,
            "project_id": execution.project_id,
            "item_type": "user-message",
            "content": "complete me",
            "receipt_status": None,
            "details_json": [],
            "sequence": 0,
            "created_at": datetime.now(),
        },
        {
            "id": f"conv-{execution.id}-1",
            "execution_id": execution.id,
            "session_id": execution.session_id,
            "project_id": execution.project_id,
            "item_type": "assistant-message",
            "content": "任务完成",
            "receipt_status": None,
            "details_json": [],
            "sequence": 1,
            "created_at": datetime.now(),
        },
    ]

    monkeypatch.setattr(agent_service_module.LLMAdapterFactory, "create", lambda _: object())

    class StubRapidExecutionLoop:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, **kwargs):
            return execution.model_copy(update={
                "status": agent_service_module.ExecutionStatus.COMPLETED,
                "result": "任务完成",
                "transcript_items": completed_transcript,
                "completed_at": datetime.now(),
            })

    monkeypatch.setattr(agent_service_module, "RapidExecutionLoop", StubRapidExecutionLoop)

    result = await service.run_execution(execution.id)

    assert result.status == agent_service_module.ExecutionStatus.COMPLETED
    assert [message.content for message in conversation_repo.saved_messages] == [
        "complete me",
        "任务完成",
    ]


@pytest.mark.asyncio
async def test_cancel_execution_returns_cancelled_execution_after_request(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    service, _ = build_service_with_repos(monkeypatch, project=project, session=session)

    sent_events = []

    class StubWsManager:
        async def send_event(self, execution_id, event_type, data):
            sent_events.append((execution_id, event_type, data))

    monkeypatch.setattr(agent_service_module, "ws_manager", StubWsManager())

    execution = await service.create_execution(
        ExecutionCreate(
            project_id="project-1",
            session_id="session-1",
            task="cancel me",
        )
    )

    started_cleanup = asyncio.Event()
    allow_cancel_to_finish = asyncio.Event()

    async def never_finishes():
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            started_cleanup.set()
            await allow_cancel_to_finish.wait()
            raise

    task = asyncio.create_task(never_finishes())
    service.running_tasks[execution.id] = task

    cancel_task = asyncio.create_task(service.cancel_execution(execution.id))
    await started_cleanup.wait()
    await asyncio.sleep(0)

    result = await cancel_task

    allow_cancel_to_finish.set()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert result.status == agent_service_module.ExecutionStatus.CANCELLED
    assert result.result == "执行已取消"
    assert any(event[1] == "execution:cancelled" for event in sent_events)
