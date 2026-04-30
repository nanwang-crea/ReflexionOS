import logging

from app.models.project import Project
from app.storage.models import ProjectModel

logger = logging.getLogger(__name__)


class ProjectRepository:
    """项目数据仓储"""

    def __init__(self, db):
        self.db = db

    def _to_project(self, model: ProjectModel) -> Project:
        return Project(
            id=model.id,
            name=model.name,
            path=model.path,
            language=model.language,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def save(self, project: Project) -> Project:
        """保存项目"""
        with self.db.get_session() as session:
            # 检查是否已存在
            existing = session.query(ProjectModel).filter_by(path=project.path).first()

            if existing:
                # 更新
                existing.name = project.name
                existing.language = project.language
                existing.config = project.config or {}
                session.flush()
                session.refresh(existing)
                logger.info("更新项目: %s", existing.id)
                return self._to_project(existing)
            else:
                # 新建
                model = ProjectModel(
                    id=project.id,
                    name=project.name,
                    path=project.path,
                    language=project.language,
                    config=project.config or {},
                )
                session.add(model)
                session.flush()
                session.refresh(model)
                logger.info("创建项目: %s", model.id)
                return self._to_project(model)

    def get(self, project_id: str) -> Project | None:
        """获取项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(id=project_id).first()
            if model:
                return self._to_project(model)
            return None

    def list_all(self) -> list[Project]:
        """列出所有项目"""
        with self.db.get_session() as session:
            models = session.query(ProjectModel).all()
            return [self._to_project(model) for model in models]

    def delete(self, project_id: str) -> bool:
        """删除项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(id=project_id).first()
            if model:
                session.delete(model)
                logger.info("删除项目: %s", project_id)
                return True
            return False
