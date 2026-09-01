"""
文件功能：会话（Session）数据仓储
文件描述：封装 sessions 表的增删改查操作，管理会话标题、首选模型、
    Agent/权限模式、事件游标（last_event_seq）等会话级状态。
核心逻辑：与其他 Repository 一致，方法可复用外部 db_session 或自行开启
    独立会话；update 采用"先查后写"模式，记录不存在时抛出
    NotFoundValueError。
"""
from app.errors import NotFoundValueError
from app.models.session import Session
from app.storage.models import SessionModel

from .base_repo import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """会话数据仓储"""

    def __init__(self, db):
        """
        函数名：__init__
        入参：
          - db: 数据库访问入口
        功能：初始化会话仓储，绑定领域模型 Session
        运行逻辑：调用父类构造函数完成初始化
        出参：无
        """
        super().__init__(db, Session)

    def create(self, session: Session, *, db_session=None) -> Session:
        """
        函数名：create
        入参：
          - session (Session): 待创建的会话领域对象
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：新建一条会话记录
        运行逻辑：将 session 的全部字段展开为 SessionModel 构造参数，写入
          后 flush + refresh 拿到数据库生成的最终字段
        出参：Session - 创建成功后的会话领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(session, db_session=managed_session)

        model = SessionModel(**session.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, session_id: str, *, db_session=None) -> Session | None:
        """
        函数名：get
        入参：
          - session_id (str): 会话主键 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按主键获取单个会话
        运行逻辑：按 id 精确匹配查询 sessions 表第一条记录
        出参：Session | None - 找到则返回会话对象，否则返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(session_id, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session_id).first()
        return self._to_domain(model)

    def list_by_project(self, project_id: str) -> list[Session]:
        """
        函数名：list_by_project
        入参：
          - project_id (str): 所属项目 ID
        功能：列出指定项目下的全部会话
        运行逻辑：按 project_id 过滤，按 updated_at 倒序排列（最近更新的
          会话排在最前）
        出参：list[Session] - 会话列表（可能为空列表）
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(SessionModel)
                .filter_by(project_id=project_id)
                .order_by(SessionModel.updated_at.desc())
                .all()
            )
            return self._to_domain_list(models)

    def update(self, session: Session, *, db_session=None) -> Session:
        """
        函数名：update
        入参：
          - session (Session): 携带最新字段值的会话领域对象（以 id 定位
            要更新的记录）
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：更新会话的标题、首选模型、模式、事件游标、活跃轮次等字段
        运行逻辑：
          1. 按 session.id 查询记录，不存在则抛出 NotFoundValueError
          2. 逐字段覆盖 title/preferred_provider_id/preferred_model_id/
             agent_mode/permission_mode/last_event_seq/active_turn_id
          3. flush + refresh 后返回最新状态
        出参：Session - 更新后的会话领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(session, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session.id).first()
        if model is None:
            raise NotFoundValueError("会话不存在")

        model.title = session.title
        model.preferred_provider_id = session.preferred_provider_id
        model.preferred_model_id = session.preferred_model_id
        model.agent_mode = session.agent_mode
        model.permission_mode = session.permission_mode
        model.last_event_seq = session.last_event_seq
        model.active_turn_id = session.active_turn_id
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def delete(self, session_id: str, *, db_session=None) -> bool:
        """
        函数名：delete
        入参：
          - session_id (str): 待删除会话的主键 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：删除会话记录（数据库外键 ondelete="CASCADE" 会级联删除该
          会话下的轮次/运行/消息/事件等关联数据）
        运行逻辑：先查询记录，存在则删除，不存在则直接返回 False
        出参：bool - 删除成功返回 True，记录不存在返回 False
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete(session_id, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session_id).first()
        if model is None:
            return False

        db_session.delete(model)
        return True
