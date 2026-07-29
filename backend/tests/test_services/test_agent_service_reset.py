from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.agent_service as agent_service_module
from app.errors import NotFoundValueError
from app.models.llm_config import LLMSettings
from app.models.session import Session
from app.observability.collector import ObservabilityCollector
from app.services.conversation_service import ConversationService
from app.services.llm_provider_service import LLMProviderService
from app.storage.database import Database
from app.storage.repositories.session_repo import SessionRepository


class _DummyConfigManager:
    def __init__(self):
        self.settings = SimpleNamespace(llm=LLMSettings())


def _build_service(tmp_path):
    db = Database(str(tmp_path / "agent-reset.db"))
    provider_service = LLMProviderService(config_manager=_DummyConfigManager())
    collector = ObservabilityCollector(
        db,
        journal_dir=tmp_path / "observability-journal",
    )
    return agent_service_module.AgentService(
        session_repo=SessionRepository(db),
        conversation_service=ConversationService(db=db),
        llm_provider_service=provider_service,
        observability_collector=collector,
    )


@pytest.mark.asyncio
async def test_reset_cancels_active_run_then_clears(monkeypatch, tmp_path):
    service = _build_service(tmp_path)
    service.session_repo.create(Session(id="s1", project_id="p1", title="会话"))

    call_order: list[str] = []

    async def fake_cancel_run(run_id):
        call_order.append(f"cancel:{run_id}")

    def fake_reset_session(session_id):
        call_order.append(f"reset:{session_id}")
        return Session(id=session_id, project_id="p1", title="会话")

    monkeypatch.setattr(service, "cancel_run", fake_cancel_run)
    monkeypatch.setattr(service.conversation_service, "reset_session", fake_reset_session)
    monkeypatch.setattr(service.conversation_service, "get_snapshot", lambda sid: object())
    monkeypatch.setattr(
        agent_service_module,
        "resolve_active_run_id_from_conversation",
        lambda snapshot: "r1",
    )

    result = await service.reset_session("s1")

    assert call_order == ["cancel:r1", "reset:s1"]
    assert result.id == "s1"


@pytest.mark.asyncio
async def test_reset_no_active_run_skips_cancel(monkeypatch, tmp_path):
    service = _build_service(tmp_path)
    service.session_repo.create(Session(id="s1", project_id="p1", title="会话"))

    cancel_mock = AsyncMock()
    reset_mock = MagicMock(return_value=Session(id="s1", project_id="p1", title="会话"))

    monkeypatch.setattr(service, "cancel_run", cancel_mock)
    monkeypatch.setattr(service.conversation_service, "reset_session", reset_mock)
    monkeypatch.setattr(service.conversation_service, "get_snapshot", lambda sid: object())
    monkeypatch.setattr(
        agent_service_module,
        "resolve_active_run_id_from_conversation",
        lambda snapshot: None,
    )

    await service.reset_session("s1")

    cancel_mock.assert_not_called()
    reset_mock.assert_called_once_with("s1")


@pytest.mark.asyncio
async def test_reset_session_not_found(monkeypatch, tmp_path):
    service = _build_service(tmp_path)

    cancel_mock = AsyncMock()
    reset_mock = MagicMock()
    monkeypatch.setattr(service, "cancel_run", cancel_mock)
    monkeypatch.setattr(service.conversation_service, "reset_session", reset_mock)

    with pytest.raises(NotFoundValueError):
        await service.reset_session("missing")

    cancel_mock.assert_not_called()
    reset_mock.assert_not_called()
