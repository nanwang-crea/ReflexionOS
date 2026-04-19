import pytest

from app.main import app
from app.models.execution import ExecutionCreate
from app.models.project import Project, ProjectCreate
from app.services.agent_service import AgentService
from app.services.project_service import ProjectService
from app.storage.database import Database
from app.storage.repositories.execution_repo import ExecutionRepository
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


@pytest.mark.asyncio
async def test_agent_service_recovers_executions_from_repository(db):
    project_repo = ProjectRepository(db)
    project = project_repo.save(Project(name="ReflexionOS", path="/tmp/reflexion"))
    repo = ExecutionRepository(db)
    first_service = AgentService(execution_repo=repo, project_repo=project_repo)
    execution = await first_service.create_execution(
        ExecutionCreate(project_id=project.id, task="inspect repo")
    )

    second_service = AgentService(execution_repo=repo, project_repo=project_repo)
    loaded = second_service.get_execution(execution.id)

    assert loaded is not None
    assert loaded.task == "inspect repo"
    assert loaded.project_id == project.id
    assert loaded.project_path == "/tmp/reflexion"


def test_agent_stop_route_is_removed():
    route_paths = {route.path for route in app.router.routes}
    assert "/api/agent/stop/{execution_id}" not in route_paths


@pytest.mark.asyncio
async def test_agent_service_rejects_unknown_project_ids(db):
    repo = ExecutionRepository(db)
    project_repo = ProjectRepository(db)
    service = AgentService(execution_repo=repo, project_repo=project_repo)

    with pytest.raises(ValueError, match="项目不存在"):
        await service.create_execution(
            ExecutionCreate(project_id="proj-missing", task="inspect repo")
        )
