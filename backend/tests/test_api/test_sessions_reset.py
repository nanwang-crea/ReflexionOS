from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.routes.sessions as sessions_route_module
import app.services.agent_service as agent_service_module
from app.main import app
from app.models.conversation import Run, RunStatus, Turn, TurnStatus
from app.models.llm_config import LLMSettings
from app.models.project import Project
from app.services.conversation_service import ConversationService
from app.services.llm_provider_service import LLMProviderService
from app.services.session_service import SessionService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


class _DummyConfigManager:
    def __init__(self):
        self.settings = SimpleNamespace(llm=LLMSettings())


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """把 session_service 与 agent_service 都绑到同一个隔离 DB。"""
    db = Database(str(tmp_path / "sessions-reset-api.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))

    session_service = SessionService(session_repo=session_repo, project_repo=project_repo)
    conversation_service = ConversationService(db=db)
    provider_service = LLMProviderService(config_manager=_DummyConfigManager())
    agent_service = agent_service_module.AgentService(
        session_repo=session_repo,
        conversation_service=conversation_service,
        llm_provider_service=provider_service,
    )

    monkeypatch.setattr(sessions_route_module, "session_service", session_service)
    monkeypatch.setattr(sessions_route_module, "agent_service", agent_service)

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            conversation_service=conversation_service,
            session_repo=session_repo,
        )


def _create_session(client) -> str:
    resp = client.post("/api/projects/project-1/sessions", json={"title": "会话"})
    assert resp.status_code == 200
    return resp.json()["id"]


def test_reset_returns_session_200(ctx):
    session_id = _create_session(ctx.client)
    ctx.conversation_service.start_turn(
        session_id=session_id,
        content="hello",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    assert ctx.session_repo.get(session_id).last_event_seq > 0

    resp = ctx.client.post(f"/api/sessions/{session_id}/reset")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == session_id
    assert body["last_event_seq"] == 0
    assert body["active_turn_id"] is None

    # 经隔离 DB 的 conversation_service 直接核实已清空
    # （HTTP 的 conversation GET 走的是模块级单例，不在本 fixture 的 DB 上）。
    assert ctx.conversation_service.get_snapshot(session_id).turns == []


def test_reset_unknown_session_returns_404(ctx):
    resp = ctx.client.post("/api/sessions/missing-session/reset")

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "not_found"
    assert "会话" in body["message"]


def test_reset_active_run_returns_400(ctx, monkeypatch):
    session_id = _create_session(ctx.client)

    # 构造活跃 run：turn.active_run_id -> RUNNING run，session.active_turn_id -> turn。
    ctx.conversation_service.turn_repo.create(Turn(
        id="t1",
        session_id=session_id,
        turn_index=0,
        root_message_id="m1",
        status=TurnStatus.RUNNING,
        active_run_id="r1",
    ))
    ctx.conversation_service.run_repo.create(Run(
        id="r1",
        session_id=session_id,
        turn_id="t1",
        attempt_index=0,
        status=RunStatus.RUNNING,
    ))
    s = ctx.session_repo.get(session_id)
    ctx.session_repo.update(s.model_copy(update={"active_turn_id": "t1"}))

    # mock cancel_run 为 no-op：真实 cancel_run 会把 run 落成 CANCELLED，
    # 那样 Service 层重校验就不再命中冲突。必须让它什么都不做。
    async def noop_cancel_run(run_id):
        return None

    monkeypatch.setattr(
        sessions_route_module.agent_service, "cancel_run", noop_cancel_run
    )

    resp = ctx.client.post(f"/api/sessions/{session_id}/reset")

    assert resp.status_code == 400
    assert resp.json()["code"] == "validation_error"
    # 冲突路径不删数据
    assert len(ctx.conversation_service.turn_repo.list_by_session(session_id)) == 1
