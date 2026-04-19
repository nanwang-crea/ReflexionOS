from pathlib import Path
from typing import Dict, List, Optional

from app.models.project import Project, ProjectCreate
from app.storage.database import db
from app.storage.repositories.project_repo import ProjectRepository


class ProjectService:
    """项目管理服务"""

    def __init__(self, repo: Optional[ProjectRepository] = None):
        self.repo = repo or ProjectRepository(db)

    def create_project(self, project_create: ProjectCreate) -> Project:
        """创建项目"""
        project = Project(**project_create.model_dump())
        return self.repo.save(project)

    def get_project(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        return self.repo.get(project_id)

    def list_projects(self) -> List[Project]:
        """列出所有项目"""
        return self.repo.list_all()

    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        return self.repo.delete(project_id)

    def get_project_structure(self, project_id: str) -> Dict:
        """获取项目结构"""
        project = self.get_project(project_id)
        if not project:
            return {}

        project_path = Path(project.path)
        if not project_path.exists():
            return {}

        structure = []
        for item in project_path.rglob("*"):
            if item.is_file() and not item.name.startswith('.'):
                structure.append({
                    "name": item.name,
                    "path": str(item.relative_to(project_path)),
                    "type": "file"
                })

        return {"files": structure[:100]}


project_service = ProjectService()
