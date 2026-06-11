from app.errors import NotFoundValueError
from app.ids import new_session_id
from app.models.session import DEFAULT_SESSION_TITLE, Session, SessionCreate, SessionUpdate
from app.storage.database import db as default_db
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


class SessionService:
    def __init__(
        self,
        db=None,
        session_repo: SessionRepository | None = None,
        project_repo: ProjectRepository | None = None,
    ):
        resolved_db = db
        if resolved_db is None:
            resolved_db = getattr(session_repo, "db", None) or getattr(project_repo, "db", None)
        if resolved_db is None and session_repo is None and project_repo is None:
            resolved_db = default_db

        self.db = resolved_db
        self.session_repo = session_repo or SessionRepository(self.db)
        self.project_repo = project_repo or ProjectRepository(self.db)

    def create_session(self, project_id: str, payload: SessionCreate) -> Session:
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
        self._get_project_or_raise(project_id)
        return self.session_repo.list_by_project(project_id)

    def get_session(self, session_id: str) -> Session | None:
        return self.session_repo.get(session_id)

    def get_session_or_raise(self, session_id: str) -> Session:
        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")
        return session

    def update_session(self, session_id: str, payload: SessionUpdate) -> Session:
        session = self.session_repo.get(session_id)
        if not session:
            raise NotFoundValueError("会话不存在")

        payload_data = payload.model_dump(exclude_unset=True)
        updated_session = session.model_copy(update=payload_data)
        return self.session_repo.update(updated_session)

    def delete_session(self, session_id: str) -> bool:
        if not self.session_repo.delete(session_id):
            raise NotFoundValueError("会话不存在")
        return True

    def _get_project_or_raise(self, project_id: str):
        project = self.project_repo.get(project_id)
        if not project:
            raise NotFoundValueError("项目不存在")
        return project


session_service = SessionService()
