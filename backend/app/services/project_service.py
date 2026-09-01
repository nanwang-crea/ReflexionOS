"""项目管理服务：负责项目（本地代码仓库工作区）的创建、查询、列表和删除，是 project 领域的业务入口。"""

from app.errors import NotFoundValueError
from app.models.project import Project, ProjectCreate
from app.storage.database import db
from app.storage.repositories.project_repo import ProjectRepository


class ProjectService:
    """项目管理服务"""

    def __init__(self, repo: ProjectRepository | None = None):
        """初始化服务。
        输入：repo（项目仓储实例，缺省时使用全局 db 构建默认 ProjectRepository，便于测试注入 mock repo）
        """
        self.repo = repo or ProjectRepository(db)

    def create_project(self, project_create: ProjectCreate) -> Project:
        """创建项目。
        输入：project_create（创建参数，含名称、本地路径等）
        逻辑：由 ProjectCreate 构建完整 Project 模型并持久化
        输出：新建的 Project 对象
        """
        project = Project(**project_create.model_dump())
        return self.repo.save(project)

    def get_project_or_raise(self, project_id: str) -> Project:
        """按 ID 查询项目，不存在则抛异常。
        输入：project_id
        输出：Project 对象
        异常：NotFoundValueError（项目不存在）
        """
        project = self.repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")
        return project

    def get_project_path(self, project_id: str) -> str:
        """获取项目对应的本地文件系统路径，供 git/文件操作等服务定位工作目录使用。
        输入：project_id
        输出：项目本地路径字符串
        异常：NotFoundValueError（项目不存在）
        """
        return self.get_project_or_raise(project_id).path

    def list_projects(self) -> list[Project]:
        """列出所有项目"""
        return self.repo.list_all()

    def delete_project_or_raise(self, project_id: str) -> None:
        """删除指定项目，不存在则抛异常。
        输入：project_id
        输出：无
        异常：NotFoundValueError（项目不存在）
        """
        if not self.repo.delete(project_id):
            raise NotFoundValueError("项目不存在")


project_service = ProjectService()
