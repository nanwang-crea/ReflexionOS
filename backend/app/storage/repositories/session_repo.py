from app.errors import NotFoundValueError
from app.models.session import Session
from app.storage.models import SessionModel

from .base_repo import BaseRepository


class SessionRepository(BaseRepository[Session]):
    def __init__(self, db):
        super().__init__(db, Session)

    def create(self, session: Session, *, db_session=None) -> Session:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(session, db_session=managed_session)

        model = SessionModel(**session.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, session_id: str, *, db_session=None) -> Session | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(session_id, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session_id).first()
        return self._to_domain(model)

    def list_by_project(self, project_id: str) -> list[Session]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(SessionModel)
                .filter_by(project_id=project_id)
                .order_by(SessionModel.updated_at.desc())
                .all()
            )
            return self._to_domain_list(models)

    def update(self, session: Session, *, db_session=None) -> Session:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(session, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session.id).first()
        if model is None:
            raise NotFoundValueError("会话不存在")

        model.title = session.title
        model.preferred_provider_id = session.preferred_provider_id
        model.preferred_model_id = session.preferred_model_id
        model.last_event_seq = session.last_event_seq
        model.active_turn_id = session.active_turn_id
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def delete(self, session_id: str, *, db_session=None) -> bool:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete(session_id, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session_id).first()
        if model is None:
            return False

        db_session.delete(model)
        return True
