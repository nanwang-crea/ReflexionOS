from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.project import Project
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.services.session_service import SessionService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "conversation-api.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_repo.create(Session(id="session-1", project_id="project-1", title="需求讨论"))

    session_service = SessionService(session_repo=session_repo, project_repo=project_repo)
    conversation_service = ConversationService(db=db)
    conversation_service.start_turn(
        session_id="session-1",
        content="请总结今天进展",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(Path("/tmp/reflexion")),
    )

    import app.api.routes.sessions as sessions_route_module

    monkeypatch.setattr(sessions_route_module, "session_service", session_service)
    monkeypatch.setattr(sessions_route_module, "conversation_service", conversation_service)

    with TestClient(app) as test_client:
        yield test_client


def test_get_conversation_snapshot_returns_normalized_entities(client):
    response = client.get("/api/sessions/session-1/conversation")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"session", "turns", "runs", "messages"}
    assert "rounds" not in payload
    assert payload["session"]["id"] == "session-1"
    assert payload["session"]["last_event_seq"] == 3
    assert len(payload["turns"]) == 1
    assert len(payload["runs"]) == 1
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["message_type"] == "user_message"
    assert payload["messages"][0]["turn_message_index"] == 1


def test_get_conversation_snapshot_returns_404_for_missing_session(client):
    response = client.get("/api/sessions/missing-session/conversation")

    assert response.status_code == 404
    assert response.json() == {"detail": "会话不存在"}
