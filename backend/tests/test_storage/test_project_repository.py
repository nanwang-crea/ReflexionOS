from app.models.project import Project
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository


def test_save_existing_path_returns_persisted_project(tmp_path):
    db = Database(str(tmp_path / "project-repository.db"))
    repo = ProjectRepository(db)
    path = "/tmp/reflexion"

    first = repo.save(Project(id="project-1", name="ReflexionOS", path=path))
    second = repo.save(Project(id="project-2", name="ReflexionOS Updated", path=path, language="python"))

    assert second.id == first.id
    assert second.name == "ReflexionOS Updated"
    assert second.language == "python"
    assert repo.get("project-2") is None
    assert [project.id for project in repo.list_all()] == [first.id]

    persisted = repo.get(first.id)
    assert persisted is not None
    assert persisted.name == "ReflexionOS Updated"
    assert persisted.language == "python"
