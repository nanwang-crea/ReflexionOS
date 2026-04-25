from app.models.conversation import ConversationEvent
from app.storage.models import ConversationEventModel


class ConversationEventRepository:
    def __init__(self, db):
        self.db = db

    def append(self, event: ConversationEvent, *, db_session=None) -> ConversationEvent:
        return self.append_many([event], db_session=db_session)[0]

    def append_many(
        self,
        events: list[ConversationEvent],
        *,
        db_session=None,
        start_seq: int | None = None,
    ) -> list[ConversationEvent]:
        if not events:
            return []

        session_id = events[0].session_id
        if any(event.session_id != session_id for event in events):
            raise ValueError("同批事件必须属于同一个会话")

        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.append_many(events, db_session=managed_session, start_seq=start_seq)

        models: list[ConversationEventModel] = []
        if start_seq is None:
            max_seq = (
                db_session.query(ConversationEventModel.seq)
                .filter_by(session_id=session_id)
                .order_by(ConversationEventModel.seq.desc())
                .limit(1)
                .scalar()
            ) or 0
            next_seq = max_seq + 1
        else:
            next_seq = start_seq
        for event in events:
            model = ConversationEventModel(
                **event.model_dump(exclude={"seq"}),
                seq=next_seq,
            )
            db_session.add(model)
            models.append(model)
            next_seq += 1

        db_session.flush()
        for model in models:
            db_session.refresh(model)
        return [ConversationEvent.model_validate(model) for model in models]

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

    def first_seq(self, session_id: str, *, db_session=None) -> int | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.first_seq(session_id, db_session=managed_session)

        return (
            db_session.query(ConversationEventModel.seq)
            .filter_by(session_id=session_id)
            .order_by(ConversationEventModel.seq.asc())
            .limit(1)
            .scalar()
        )

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        if not turn_ids:
            return 0

        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

        deleted = (
            db_session.query(ConversationEventModel)
            .filter(ConversationEventModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)
