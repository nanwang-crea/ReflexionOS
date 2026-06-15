from io import BytesIO
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
    db = Database(str(tmp_path / "upload-api.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))

    service = SessionService(session_repo=session_repo, project_repo=project_repo)

    import app.api.routes.sessions as sessions_route_module

    monkeypatch.setattr(sessions_route_module, "session_service", service)

    # Also patch upload route if it uses session_repo
    try:
        import app.api.routes.upload as upload_route_module
        monkeypatch.setattr(upload_route_module, "session_repo", session_repo)
        monkeypatch.setattr(upload_route_module, "db", db)
    except ImportError:
        pass

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_session_id(client):
    """Create a test session and return its ID"""
    response = client.post(
        "/api/projects/project-1/sessions",
        json={"title": "测试会话"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_upload_image_success(client, test_session_id):
    """测试成功上传图片"""
    # 创建一个简单的图片数据
    image_data = b"fake image content"
    files = {"file": ("test.png", BytesIO(image_data), "image/png")}

    response = client.post(
        f"/api/sessions/{test_session_id}/upload",
        files=files
    )

    assert response.status_code == 200
    data = response.json()
    assert "attachment_id" in data
    assert "file_path" in data
    assert "file_size" in data
    assert data["file_size"] == len(image_data)


def test_upload_non_image_fails(client, test_session_id):
    """测试上传非图片文件失败"""
    text_data = b"not an image"
    files = {"file": ("test.txt", BytesIO(text_data), "text/plain")}

    response = client.post(
        f"/api/sessions/{test_session_id}/upload",
        files=files
    )

    assert response.status_code == 400
    assert "只支持图片文件" in response.json()["detail"]


def test_upload_large_image_fails(client, test_session_id):
    """测试上传超大图片失败"""
    large_data = b"x" * (11 * 1024 * 1024)  # 11MB
    files = {"file": ("large.png", BytesIO(large_data), "image/png")}

    response = client.post(
        f"/api/sessions/{test_session_id}/upload",
        files=files
    )

    assert response.status_code == 400
    assert "大小超过限制" in response.json()["detail"]


def test_upload_missing_session_fails(client):
    """测试上传到不存在的会话失败"""
    image_data = b"fake image content"
    files = {"file": ("test.png", BytesIO(image_data), "image/png")}

    response = client.post(
        "/api/sessions/nonexistent-session/upload",
        files=files
    )

    assert response.status_code == 404
    assert "会话不存在" in response.json()["detail"]
