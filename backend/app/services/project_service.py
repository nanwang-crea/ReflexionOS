from typing import List, Optional, Dict
from app.models.project import Project, ProjectCreate
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ProjectService:
    """项目管理服务"""
    
    def __init__(self, storage_path: str = ".reflexion/projects.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.projects: Dict[str, Project] = self._load_projects()
    
    def _load_projects(self) -> Dict[str, Project]:
        """从存储加载项目"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {k: Project(**v) for k, v in data.items()}
            except Exception as e:
                logger.error(f"加载项目失败: {str(e)}")
        return {}
    
    def _save_projects(self) -> None:
        """保存项目到存储"""
        try:
            data = {k: v.model_dump() for k, v in self.projects.items()}
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            logger.info("项目数据已保存")
        except Exception as e:
            logger.error(f"保存项目失败: {str(e)}")
    
    def create_project(self, project_create: ProjectCreate) -> Project:
        """创建项目"""
        project = Project(**project_create.model_dump())
        self.projects[project.id] = project
        self._save_projects()
        logger.info(f"创建项目: {project.id} - {project.name}")
        return project
    
    def get_project(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        return self.projects.get(project_id)
    
    def list_projects(self) -> List[Project]:
        """列出所有项目"""
        return list(self.projects.values())
    
    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        if project_id in self.projects:
            del self.projects[project_id]
            self._save_projects()
            logger.info(f"删除项目: {project_id}")
            return True
        return False
    
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
