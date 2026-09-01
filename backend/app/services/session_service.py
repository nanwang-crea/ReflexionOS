"""会话管理服务：负责项目下会话（Session）的创建、查询、更新和删除，并校验所属项目是否存在。"""

from app.errors import NotFoundValueError
from app.ids import new_session_id
from app.models.session import DEFAULT_SESSION_TITLE, Session, SessionCreate, SessionUpdate
from app.storage.database import db as default_db
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


class SessionService:
    """会话服务：会话的增删改查均围绕 session_repo，涉及项目归属校验时复用 project_repo。"""

    def __init__(
        self,
        db=None,
        session_repo: SessionRepository | None = None,
        project_repo: ProjectRepository | None = None,
    ):
        """初始化服务，支持依赖注入以便测试。
        输入：
          - db：数据库实例，缺省时优先复用传入的 repo 自带的 db，都未传时才回退到全局 default_db
          - session_repo / project_repo：可选的仓储实例，缺省时基于 resolved_db 自动构建
        逻辑：优先保证 session_repo/project_repo 与传入的 db 一致，避免出现多个 db 实例导致数据不一致
        """
        resolved_db = db
        if resolved_db is None:
            resolved_db = getattr(session_repo, "db", None) or getattr(project_repo, "db", None)
        if resolved_db is None and session_repo is None and project_repo is None:
            resolved_db = default_db

        self.db = resolved_db
        self.session_repo = session_repo or SessionRepository(self.db)
        self.project_repo = project_repo or ProjectRepository(self.db)

    def create_session(self, project_id: str, payload: SessionCreate) -> Session:
        """在指定项目下创建新会话。
        输入：project_id（所属项目 ID）、payload（创建参数，含标题、首选供应商/模型等，均可选）
        逻辑：
          1. 校验项目是否存在；
          2. 生成新 session_id，标题缺省时使用 DEFAULT_SESSION_TITLE；
          3. 持久化会话记录。
        输出：新建的 Session 对象
        异常：NotFoundValueError（项目不存在）
        """
        self._get_project_or_raise(project_id)

        session = Session(
            id=new_session_id(),
            project_id=project_id,
            title=payload.title or DEFAULT_SESSION_TITLE,
            preferred_provider_id=payload.preferred_provider_id,
            preferred_model_id=payload.preferred_model_id,
        )
        return self.session_repo.create(session)

    def list_project_sessions(self, project_id: str) -> list[Session]:
        """列出指定项目下的所有会话。
        输入：project_id
        输出：Session 列表
        异常：NotFoundValueError（项目不存在）
        """
        self._get_project_or_raise(project_id)
        return self.session_repo.list_by_project(project_id)

    def get_session(self, session_id: str) -> Session | None:
        """按 ID 查询会话，不存在时返回 None（不抛异常）。
        输入：session_id
        输出：Session 对象或 None
        """
        return self.session_repo.get(session_id)

    def get_session_or_raise(self, session_id: str) -> Session:
        """按 ID 查询会话，不存在则抛异常。
        输入：session_id
        输出：Session 对象
        异常：NotFoundValueError（会话不存在）
        """
        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")
        return session

    def update_session(self, session_id: str, payload: SessionUpdate) -> Session:
        """更新会话（部分字段更新）。
        输入：session_id、payload（更新参数，仅显式设置的字段会被应用）
        逻辑：以 exclude_unset=True 提取 payload 中实际传入的字段，覆盖到原会话上
        输出：更新后的 Session 对象
        异常：NotFoundValueError（会话不存在）
        """
        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")

        payload_data = payload.model_dump(exclude_unset=True)
        updated_session = session.model_copy(update=payload_data)
        return self.session_repo.update(updated_session)

    def delete_session(self, session_id: str) -> bool:
        """删除指定会话。
        输入：session_id
        输出：True（删除成功）
        异常：NotFoundValueError（会话不存在）
        """
        if not self.session_repo.delete(session_id):
            raise NotFoundValueError("会话不存在")
        return True

    def _get_project_or_raise(self, project_id: str):
        """内部辅助：校验项目是否存在，不存在则抛异常。
        输入：project_id
        输出：Project 对象
        异常：NotFoundValueError（项目不存在）
        """
        project = self.project_repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")
        return project


session_service = SessionService()
