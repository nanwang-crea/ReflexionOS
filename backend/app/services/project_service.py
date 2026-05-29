from app.errors import NotFoundValueError
from app.models.project import Project, ProjectCreate
from app.storage.database import db
from app.storage.repositories.project_repo import ProjectRepository


class ProjectService:
    """项目管理服务"""

    def __init__(self, repo: ProjectRepository | None = None):
        self.repo = repo or ProjectRepository(db)

    def create_project(self, project_create: ProjectCreate) -> Project:
        """创建项目"""
        project = Project(**project_create.model_dump())
        return self.repo.save(project)

    def get_project_or_raise(self, project_id: str) -> Project:
        project = self.repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")
        return project

    def get_project_path(self, project_id: str) -> str:
        return self.get_project_or_raise(project_id).path

    def list_projects(self) -> list[Project]:
        """列出所有项目"""
        return self.repo.list_all()

    def delete_project_or_raise(self, project_id: str) -> None:
        if not self.repo.delete(project_id):
            raise NotFoundValueError("项目不存在")


project_service = ProjectService()
