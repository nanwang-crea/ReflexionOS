from uuid import uuid4

from pydantic import BaseModel

from app.models.session import Session
from app.storage.database import db
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


class SessionCreate(BaseModel):
    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None


class SessionService:
    def __init__(
        self,
        session_repo: SessionRepository | None = None,
        project_repo: ProjectRepository | None = None,
    ):
        self.session_repo = session_repo or SessionRepository(db)
        self.project_repo = project_repo or ProjectRepository(db)

    def create_session(self, project_id: str, payload: SessionCreate) -> Session:
        self._get_project_or_raise(project_id)

        session = Session(
            id=f"session-{uuid4().hex[:8]}",
            project_id=project_id,
            title=payload.title or "新建聊天",
            preferred_provider_id=payload.preferred_provider_id,
            preferred_model_id=payload.preferred_model_id,
        )
        return self.session_repo.create(session)

    def list_project_sessions(self, project_id: str) -> list[Session]:
        self._get_project_or_raise(project_id)
        return self.session_repo.list_by_project(project_id)

    def get_session(self, session_id: str) -> Session | None:
        return self.session_repo.get(session_id)

    def update_session(self, session_id: str, payload: SessionUpdate) -> Session:
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("会话不存在")

        payload_data = payload.model_dump(exclude_unset=True)
        updated_session = session.model_copy(
            update={
                "title": payload_data.get("title", session.title),
                "preferred_provider_id": payload_data.get(
                    "preferred_provider_id",
                    session.preferred_provider_id,
                ),
                "preferred_model_id": payload_data.get(
                    "preferred_model_id",
                    session.preferred_model_id,
                ),
            }
        )
        return self.session_repo.update(updated_session)

    def delete_session(self, session_id: str) -> bool:
        if not self.session_repo.delete(session_id):
            raise ValueError("会话不存在")
        return True

    def _get_project_or_raise(self, project_id: str):
        project = self.project_repo.get(project_id)
        if not project:
            raise ValueError("项目不存在")
        return project


session_service = SessionService()
