import logging

from app.models.project import Project
from app.storage.models import ProjectModel

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class ProjectRepository(BaseRepository[Project]):
    """项目数据仓储"""

    def __init__(self, db):
        super().__init__(db, Project)

    def save(self, project: Project, *, db_session=None) -> Project:
        """保存项目（按 path 去重：已存在则更新，否则新建）"""
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.save(project, db_session=managed_session)

        existing = db_session.query(ProjectModel).filter_by(path=project.path).first()

        if existing:
            existing.name = project.name
            existing.language = project.language
            existing.config = project.config or {}
            db_session.flush()
            db_session.refresh(existing)
            logger.info("更新项目: %s", existing.id)
            return self._to_domain(existing)

        model = ProjectModel(
            id=project.id,
            name=project.name,
            path=project.path,
            language=project.language,
            config=project.config or {},
        )
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        logger.info("创建项目: %s", model.id)
        return self._to_domain(model)

    def get(self, project_id: str, *, db_session=None) -> Project | None:
        """获取项目"""
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(project_id, db_session=managed_session)

        model = db_session.query(ProjectModel).filter_by(id=project_id).first()
        return self._to_domain(model)

    def list_all(self, *, db_session=None) -> list[Project]:
        """列出所有项目"""
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.list_all(db_session=managed_session)

        models = db_session.query(ProjectModel).all()
        return self._to_domain_list(models)

    def delete(self, project_id: str, *, db_session=None) -> bool:
        """删除项目"""
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete(project_id, db_session=managed_session)

        model = db_session.query(ProjectModel).filter_by(id=project_id).first()
        if model:
            db_session.delete(model)
            logger.info("删除项目: %s", project_id)
            return True
        return False
