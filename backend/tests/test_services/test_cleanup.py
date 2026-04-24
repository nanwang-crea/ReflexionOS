import pytest

from app.main import app
from app.models.project import Project, ProjectCreate
from app.services.project_service import ProjectService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "cleanup.db")
    return Database(db_path)


def test_project_service_reads_projects_from_repository(db):
    repo = ProjectRepository(db)
    first_service = ProjectService(repo=repo)
    created = first_service.create_project(ProjectCreate(name="ReflexionOS", path="/tmp/reflexion"))

    second_service = ProjectService(repo=repo)
    loaded = second_service.get_project(created.id)

    assert loaded is not None
    assert loaded.path == "/tmp/reflexion"
    assert [project.id for project in second_service.list_projects()] == [created.id]


def test_legacy_agent_routes_are_not_registered():
    route_paths = {route.path for route in app.router.routes}
    assert "/api/agent/status/{execution_id}" not in route_paths
    assert "/api/agent/history/{project_id}" not in route_paths
    assert "/api/agent/cancel/{execution_id}" not in route_paths


def test_legacy_history_route_is_not_registered():
    route_paths = {route.path for route in app.router.routes}
    assert "/api/sessions/{session_id}/history" not in route_paths


def test_websocket_status_route_is_removed():
    route_paths = {route.path for route in app.router.routes}
    assert "/ws/status" not in route_paths


def test_project_model_is_still_available_after_cleanup():
    project = Project(name="ReflexionOS", path="/tmp/reflexion")
    assert project.name == "ReflexionOS"
