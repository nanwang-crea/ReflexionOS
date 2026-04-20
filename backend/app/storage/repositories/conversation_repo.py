from typing import Iterable

from app.models.conversation import ConversationMessage
from app.storage.models import ConversationModel


class ConversationRepository:
    def __init__(self, db):
        self.db = db

    def save_messages(self, messages: Iterable[ConversationMessage]) -> None:
        with self.db.get_session() as session:
            for message in messages:
                existing = session.query(ConversationModel).filter_by(id=message.id).first()
                if existing:
                    existing.execution_id = message.execution_id
                    existing.session_id = message.session_id
                    existing.project_id = message.project_id
                    existing.item_type = message.item_type
                    existing.content = message.content
                    existing.receipt_status = message.receipt_status
                    existing.details_json = message.details_json
                    existing.sequence = message.sequence
                    existing.timestamp = message.created_at
                    continue

                session.add(ConversationModel(
                    id=message.id,
                    execution_id=message.execution_id,
                    session_id=message.session_id,
                    project_id=message.project_id,
                    item_type=message.item_type,
                    content=message.content,
                    receipt_status=message.receipt_status,
                    details_json=message.details_json,
                    sequence=message.sequence,
                    timestamp=message.created_at,
                ))

    def list_by_session(self, session_id: str) -> list[ConversationMessage]:
        with self.db.get_session() as session:
            models = session.query(ConversationModel).filter_by(
                session_id=session_id
            ).order_by(
                ConversationModel.timestamp.asc(),
                ConversationModel.sequence.asc()
            ).all()

            return [
                ConversationMessage(
                    id=model.id,
                    execution_id=model.execution_id,
                    session_id=model.session_id,
                    project_id=model.project_id,
                    item_type=model.item_type,
                    content=model.content,
                    receipt_status=model.receipt_status,
                    details_json=model.details_json or [],
                    sequence=model.sequence,
                    created_at=model.timestamp,
                )
                for model in models
            ]
