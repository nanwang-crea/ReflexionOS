from app.models.conversation import ConversationEvent
from app.storage.models import ConversationEventModel


class ConversationEventRepository:
    def __init__(self, db):
        self.db = db

    def append(self, event: ConversationEvent) -> ConversationEvent:
        with self.db.get_session() as db_session:
            max_seq = (
                db_session.query(ConversationEventModel.seq)
                .filter_by(session_id=event.session_id)
                .order_by(ConversationEventModel.seq.desc())
                .limit(1)
                .scalar()
            ) or 0
            model = ConversationEventModel(
                **event.model_dump(exclude={"seq"}),
                seq=max_seq + 1,
            )
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return ConversationEvent.model_validate(model)

    def get(self, event_id: str) -> ConversationEvent | None:
        with self.db.get_session() as db_session:
            model = db_session.query(ConversationEventModel).filter_by(id=event_id).first()
            return ConversationEvent.model_validate(model) if model else None

    def list_after_seq(self, session_id: str, after_seq: int) -> list[ConversationEvent]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(ConversationEventModel)
                .filter(
                    ConversationEventModel.session_id == session_id,
                    ConversationEventModel.seq > after_seq,
                )
                .order_by(ConversationEventModel.seq.asc())
                .all()
            )
            return [ConversationEvent.model_validate(model) for model in models]
