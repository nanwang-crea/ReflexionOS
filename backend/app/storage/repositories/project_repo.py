from typing import List, Optional
from app.storage.models import ProjectModel
from app.models.project import Project
import logging

logger = logging.getLogger(__name__)


class ProjectRepository:
    """项目数据仓储"""
    
    def __init__(self, db):
        self.db = db
    
    def save(self, project: Project) -> Project:
        """保存项目"""
        with self.db.get_session() as session:
            # 检查是否已存在
            existing = session.query(ProjectModel).filter_by(
                path=project.path
            ).first()
            
            if existing:
                # 更新
                existing.name = project.name
                existing.language = project.language
                existing.config = {}
                logger.info(f"更新项目: {project.id}")
            else:
                # 新建
                model = ProjectModel(
                    id=project.id,
                    name=project.name,
                    path=project.path,
                    language=project.language,
                    config={}
                )
                session.add(model)
                logger.info(f"创建项目: {project.id}")
            
            return project
    
    def get(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(id=project_id).first()
            if model:
                return Project(
                    id=model.id,
                    name=model.name,
                    path=model.path,
                    language=model.language,
                    created_at=model.created_at,
                    updated_at=model.updated_at
                )
            return None
    
    def get_by_path(self, path: str) -> Optional[Project]:
        """根据路径获取项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(path=path).first()
            if model:
                return Project(
                    id=model.id,
                    name=model.name,
                    path=model.path,
                    language=model.language,
                    created_at=model.created_at,
                    updated_at=model.updated_at
                )
            return None
    
    def list_all(self) -> List[Project]:
        """列出所有项目"""
        with self.db.get_session() as session:
            models = session.query(ProjectModel).order_by(
                ProjectModel.updated_at.desc()
            ).all()
            
            return [
                Project(
                    id=m.id,
                    name=m.name,
                    path=m.path,
                    language=m.language,
                    created_at=m.created_at,
                    updated_at=m.updated_at
                )
                for m in models
            ]
    
    def delete(self, project_id: str) -> bool:
        """删除项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(id=project_id).first()
            if model:
                session.delete(model)
                logger.info(f"删除项目: {project_id}")
                return True
            return False
