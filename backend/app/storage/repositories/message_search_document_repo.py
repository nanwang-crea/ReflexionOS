from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.storage.models import MessageSearchDocumentModel


class MessageSearchDocument(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    turn_id: str
    run_id: str | None = None
    role: str
    message_type: str
    turn_index: int
    turn_message_index: int
    search_text: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MessageSearchDocumentRepository:
    def __init__(self, db):
        self.db = db

    def get(self, message_id: str, *, db_session=None) -> MessageSearchDocument | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(message_id, db_session=managed_session)

        model = (
            db_session.query(MessageSearchDocumentModel).filter_by(message_id=message_id).first()
        )
        return MessageSearchDocument.model_validate(model) if model else None

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
        return MessageSearchDocument.model_validate(model)
