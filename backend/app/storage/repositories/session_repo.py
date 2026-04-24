
from app.models.session import Session
from app.storage.models import SessionModel


class SessionRepository:
    def __init__(self, db):
        self.db = db

    def create(self, session: Session, *, db_session=None) -> Session:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(session, db_session=managed_session)

        model = SessionModel(**session.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return Session.model_validate(model)

    def get(self, session_id: str, *, db_session=None) -> Session | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(session_id, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session_id).first()
        return Session.model_validate(model) if model else None

    def list_by_project(self, project_id: str) -> list[Session]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(SessionModel)
                .filter_by(project_id=project_id)
                .order_by(SessionModel.updated_at.desc())
                .all()
            )
            return [Session.model_validate(model) for model in models]

    def update(self, session: Session, *, db_session=None) -> Session:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(session, db_session=managed_session)

        model = db_session.query(SessionModel).filter_by(id=session.id).first()
        if model is None:
            raise ValueError("会话不存在")

        model.title = session.title
        model.preferred_provider_id = session.preferred_provider_id
        model.preferred_model_id = session.preferred_model_id
        model.last_event_seq = session.last_event_seq
        model.active_turn_id = session.active_turn_id
        db_session.flush()
        db_session.refresh(model)
        return Session.model_validate(model)

    def delete(self, session_id: str) -> bool:
        with self.db.get_session() as db_session:
            model = db_session.query(SessionModel).filter_by(id=session_id).first()
            if model is None:
                return False

            db_session.delete(model)
            return True
