from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.project import Project
from app.services.session_service import SessionService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "sessions-api.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))

    service = SessionService(session_repo=session_repo, project_repo=project_repo)

    import app.api.routes.sessions as sessions_route_module

    monkeypatch.setattr(sessions_route_module, "session_service", service)
    with TestClient(app) as test_client:
        yield test_client


def test_get_project_sessions_returns_sessions(client):
    create_response = client.post(
        "/api/projects/project-1/sessions",
        json={
            "title": "需求讨论",
            "preferred_provider_id": "provider-a",
            "preferred_model_id": "model-a",
        },
    )

    assert create_response.status_code == 200

    response = client.get("/api/projects/project-1/sessions")

    assert response.status_code == 200
    assert response.json()[0]["project_id"] == "project-1"
    assert response.json()[0]["title"] == "需求讨论"


def test_create_session_rejects_missing_project(client):
    response = client.post("/api/projects/missing-project/sessions", json={"title": "新建聊天"})

    assert response.status_code == 404
    assert response.json() == {"detail": "项目不存在"}


def test_get_project_sessions_returns_404_for_missing_project(client):
    response = client.get("/api/projects/missing-project/sessions")

    assert response.status_code == 404
    assert response.json() == {"detail": "项目不存在"}


def test_get_session_returns_session_resource(client):
    create_response = client.post(
        "/api/projects/project-1/sessions",
        json={
            "title": "需求讨论",
            "preferred_provider_id": "provider-a",
            "preferred_model_id": "model-a",
        },
    )
    session_id = create_response.json()["id"]

    response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["id"] == session_id
    assert response.json()["title"] == "需求讨论"


def test_get_session_returns_404_for_missing_resource(client):
    response = client.get("/api/sessions/missing-session")

    assert response.status_code == 404
    assert response.json() == {"detail": "会话不存在"}


def test_patch_session_updates_existing_resource(client):
    create_response = client.post(
        "/api/projects/project-1/sessions",
        json={
            "title": "旧标题",
            "preferred_provider_id": "provider-a",
            "preferred_model_id": "model-a",
        },
    )
    session_id = create_response.json()["id"]

    response = client.patch(
        f"/api/sessions/{session_id}",
        json={"title": "新标题", "preferred_provider_id": "provider-b", "preferred_model_id": None},
    )

    assert response.status_code == 200
    assert response.json()["id"] == session_id
    assert response.json()["title"] == "新标题"
    assert response.json()["preferred_provider_id"] == "provider-b"
    assert response.json()["preferred_model_id"] is None


def test_patch_session_preserves_omitted_preference_fields(client):
    create_response = client.post(
        "/api/projects/project-1/sessions",
        json={
            "title": "旧标题",
            "preferred_provider_id": "provider-a",
            "preferred_model_id": "model-a",
        },
    )
    session_id = create_response.json()["id"]

    response = client.patch(f"/api/sessions/{session_id}", json={"title": "只改标题"})

    assert response.status_code == 200
    assert response.json()["id"] == session_id
    assert response.json()["title"] == "只改标题"
    assert response.json()["preferred_provider_id"] == "provider-a"
    assert response.json()["preferred_model_id"] == "model-a"


def test_patch_session_returns_404_for_missing_resource(client):
    response = client.patch("/api/sessions/missing-session", json={"title": "新标题"})

    assert response.status_code == 404
    assert response.json() == {"detail": "会话不存在"}


def test_delete_session_removes_existing_resource(client):
    create_response = client.post(
        "/api/projects/project-1/sessions",
        json={"title": "需求讨论"},
    )
    session_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/sessions/{session_id}")
    get_response = client.get(f"/api/sessions/{session_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"message": "会话已删除"}
    assert get_response.status_code == 404


def test_delete_session_returns_404_for_missing_resource(client):
    response = client.delete("/api/sessions/missing-session")

    assert response.status_code == 404
    assert response.json() == {"detail": "会话不存在"}


def test_history_endpoint_is_removed(client):
    response = client.get("/api/sessions/session-1/history")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
