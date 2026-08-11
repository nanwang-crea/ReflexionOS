from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.agent_service as agent_service_module
from app.errors import NotFoundValueError
from app.models.llm_config import LLMSettings
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.services.llm_provider_service import LLMProviderService
from app.storage.database import Database
from app.storage.repositories.session_repo import SessionRepository
from app.security.session_trust_store import TrustRule


class _DummyConfigManager:
    def __init__(self):
        self.settings = SimpleNamespace(llm=LLMSettings())


def _build_service(tmp_path):
    db = Database(str(tmp_path / "agent-reset.db"))
    provider_service = LLMProviderService(config_manager=_DummyConfigManager())
    return agent_service_module.AgentService(
        session_repo=SessionRepository(db),
        conversation_service=ConversationService(db=db),
        llm_provider_service=provider_service,
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
async def test_reset_clears_trust_rules_and_pending_approvals(monkeypatch, tmp_path):
    service = _build_service(tmp_path)
    service.session_repo.create(Session(id="s1", project_id="p1", title="会话"))
    service.trust_store.add_rule("s1", TrustRule(permission="shell", pattern="git *"))
    service.pending_approval_store.create(
        session_id="s1",
        turn_id="t1",
        run_id="r1",
        step_number=1,
        tool_call_id="c1",
        tool_name="shell",
        tool_arguments={"command": "git push"},
        approval_payload={},
    )

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
    assert service.trust_store.get_rules("s1") == []
    assert service.pending_approval_store.list_pending_approval_ids_for_session("s1") == []


@pytest.mark.asyncio
async def test_reset_failure_preserves_trust_rules_and_pending_approvals(monkeypatch, tmp_path):
    service = _build_service(tmp_path)
    service.session_repo.create(Session(id="s1", project_id="p1", title="会话"))
    service.trust_store.add_rule("s1", TrustRule(permission="shell", pattern="git *"))
    pending = service.pending_approval_store.create(
        session_id="s1",
        turn_id="t1",
        run_id="r1",
        step_number=1,
        tool_call_id="c1",
        tool_name="shell",
        tool_arguments={"command": "git push"},
        approval_payload={},
    )

    cancel_mock = AsyncMock()

    def failing_reset_session(session_id):
        raise ValueError("会话仍有运行中的任务，无法重置")

    monkeypatch.setattr(service, "cancel_run", cancel_mock)
    monkeypatch.setattr(service.conversation_service, "reset_session", failing_reset_session)
    monkeypatch.setattr(service.conversation_service, "get_snapshot", lambda sid: object())
    monkeypatch.setattr(
        agent_service_module,
        "resolve_active_run_id_from_conversation",
        lambda snapshot: None,
    )

    with pytest.raises(ValueError, match="运行中的任务"):
        await service.reset_session("s1")

    assert service.trust_store.matches("s1", "shell", "git status")
    assert service.pending_approval_store.get(pending.id).status == "pending"


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
