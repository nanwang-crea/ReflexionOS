from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.project import Project
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.services.session_service import SessionService
from app.storage.database import Database
from app.storage.repositories.message_search_document_repo import MessageSearchDocumentRepository
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


@pytest.fixture
def client_with_memory_pipeline(tmp_path, monkeypatch):
    """
    API-level fixture that exposes ConversationService so tests can assert on
    derived message search docs + compacted summary persistence.
    """

    from types import SimpleNamespace

    db = Database(str(tmp_path / "conversation-api-memory-pipeline.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(tmp_path)))
    session_repo.create(Session(id="session-1", project_id="project-1", title="需求讨论"))

    session_service = SessionService(session_repo=session_repo, project_repo=project_repo)
    conversation_service = ConversationService(db=db)

    import app.api.routes.sessions as sessions_route_module

    monkeypatch.setattr(sessions_route_module, "session_service", session_service)
    monkeypatch.setattr(sessions_route_module, "conversation_service", conversation_service)

    with TestClient(app) as test_client:
        yield SimpleNamespace(
            client=test_client,
            db=db,
            tmp_path=tmp_path,
            project_repo=project_repo,
            session_repo=session_repo,
            conversation_service=conversation_service,
        )


def test_get_conversation_snapshot_returns_normalized_entities(client):
    response = client.get("/api/sessions/session-1/conversation")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"session", "turns", "runs", "messages", "has_more", "next_before_turn_id"}
    assert "rounds" not in payload
    assert payload["session"]["id"] == "session-1"
    assert payload["session"]["last_event_seq"] >= 1
    assert payload["turns"]
    assert payload["runs"]
    assert payload["messages"]
    assert any(message["message_type"] == "user_message" for message in payload["messages"])
    assert any(message["content_text"] == "请总结今天进展" for message in payload["messages"])
    root_message_ids = {turn["root_message_id"] for turn in payload["turns"]}
    message_ids = {message["id"] for message in payload["messages"]}
    assert root_message_ids.issubset(message_ids)


def test_get_conversation_snapshot_returns_turn_cursor_metadata(client):
    response = client.get("/api/sessions/session-1/conversation")

    assert response.status_code == 200
    payload = response.json()
    assert "next_before_turn_id" in payload


def test_get_conversation_snapshot_accepts_before_turn_query(client):
    response = client.get(
        "/api/sessions/session-1/conversation",
        params={"limit": 20, "before_turn": "turn-3"},
    )

    assert response.status_code == 200


def test_get_conversation_snapshot_empty_before_turn_uses_latest_page(client):
    response = client.get(
        "/api/sessions/session-1/conversation",
        params={"limit": 20, "before_turn": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"]


def test_get_conversation_snapshot_terminal_page_has_null_next_before_turn_id(client):
    response = client.get(
        "/api/sessions/session-1/conversation",
        params={"limit": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["has_more"] is False
    assert payload["next_before_turn_id"] is None


def test_get_conversation_snapshot_returns_404_for_missing_session(client):
    response = client.get("/api/sessions/missing-session/conversation")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert "会话" in body["message"]



