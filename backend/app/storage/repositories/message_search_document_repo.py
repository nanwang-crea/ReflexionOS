from __future__ import annotations

from datetime import datetime

from app.models.message_search_document import MessageSearchDocument
from app.storage.models import MessageSearchDocumentModel

from .base_repo import BaseRepository


class MessageSearchDocumentRepository(BaseRepository[MessageSearchDocument]):
    def __init__(self, db):
        super().__init__(db, MessageSearchDocument)

    def get(self, message_id: str, *, db_session=None) -> MessageSearchDocument | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(message_id, db_session=managed_session)

        model = (
            db_session.query(MessageSearchDocumentModel).filter_by(message_id=message_id).first()
        )
        return self._to_domain(model)

    def upsert(
        self,
        *,
        message_id: str,
        session_id: str,
        turn_id: str,
        run_id: str | None,
        role: str,
        message_type: str,
        turn_index: int,
        turn_message_index: int,
        search_text: str,
        db_session=None,
    ) -> MessageSearchDocument:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.upsert(
                    message_id=message_id,
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    role=role,
                    message_type=message_type,
                    turn_index=turn_index,
                    turn_message_index=turn_message_index,
                    search_text=search_text,
                    db_session=managed_session,
                )

        model = (
            db_session.query(MessageSearchDocumentModel).filter_by(message_id=message_id).first()
        )
        now = datetime.now()
        if model is None:
            model = MessageSearchDocumentModel(
                message_id=message_id,
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                role=role,
                message_type=message_type,
                turn_index=turn_index,
                turn_message_index=turn_message_index,
                search_text=search_text,
                created_at=now,
                updated_at=now,
            )
            db_session.add(model)
        else:
            model.session_id = session_id
            model.turn_id = turn_id
            model.run_id = run_id
            model.role = role
            model.message_type = message_type
            model.turn_index = turn_index
            model.turn_message_index = turn_message_index
            model.search_text = search_text
            model.updated_at = now

        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        if not turn_ids:
            return 0

        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

        deleted = (
            db_session.query(MessageSearchDocumentModel)
            .filter(MessageSearchDocumentModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)
