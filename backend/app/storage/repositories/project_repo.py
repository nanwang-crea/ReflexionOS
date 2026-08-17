"""
文件功能：项目（Project）数据仓储
文件描述：封装 projects 表的增删改查操作，是上层服务访问项目数据的唯一
    入口，对外屏蔽 SQLAlchemy 会话（Session）细节。
核心逻辑：所有方法均支持传入外部 db_session 复用事务，未传入时自动通过
    self.db.get_session() 开启并管理一个独立会话（用完自动提交/关闭）。
"""
import logging

from app.models.project import Project
from app.storage.models import ProjectModel

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class ProjectRepository(BaseRepository[Project]):
    """项目数据仓储"""

    def __init__(self, db):
        """
        函数名：__init__
        入参：
          - db: 数据库访问入口
        功能：初始化项目仓储，绑定领域模型 Project
        运行逻辑：调用父类构造函数完成初始化
        出参：无
        """
        super().__init__(db, Project)

    def save(self, project: Project, *, db_session=None) -> Project:
        """
        函数名：save
        入参：
          - project (Project): 待保存的项目领域对象
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：保存项目（按 path 去重：已存在则更新，否则新建）
        运行逻辑：
          1. db_session 为空时，开启新会话并递归调用自身复用逻辑
          2. 按 project.path 查询 projects 表是否已存在同路径记录
          3. 若存在：更新 name/language/config 字段后 flush + refresh
          4. 若不存在：以 project 全部字段新建 ProjectModel 并写入
        出参：Project - 保存后的项目领域对象（含数据库生成/更新后的字段）
        """
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
        """
        函数名：get
        入参：
          - project_id (str): 项目主键 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按主键获取单个项目
        运行逻辑：按 id 精确匹配查询 projects 表第一条记录并转换为领域模型
        出参：Project | None - 找到则返回项目对象，否则返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(project_id, db_session=managed_session)

        model = db_session.query(ProjectModel).filter_by(id=project_id).first()
        return self._to_domain(model)

    def list_all(self, *, db_session=None) -> list[Project]:
        """
        函数名：list_all
        入参：
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：列出所有项目
        运行逻辑：无过滤条件查询 projects 表全部记录
        出参：list[Project] - 项目列表（可能为空列表）
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.list_all(db_session=managed_session)

        models = db_session.query(ProjectModel).all()
        return self._to_domain_list(models)

    def delete(self, project_id: str, *, db_session=None) -> bool:
        """
        函数名：delete
        入参：
          - project_id (str): 待删除项目的主键 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按主键删除项目
        运行逻辑：先按 id 查询记录，存在则删除并记录日志，不存在则直接返回
          False（不做任何操作）
        出参：bool - 删除成功返回 True，记录不存在返回 False
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete(project_id, db_session=managed_session)

        model = db_session.query(ProjectModel).filter_by(id=project_id).first()
        if model:
            db_session.delete(model)
            logger.info("删除项目: %s", project_id)
            return True
        return False
