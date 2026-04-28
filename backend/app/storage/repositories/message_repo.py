from app.models.conversation import Message, MessageType, StreamState
from app.storage.models import MessageModel, TurnModel
from sqlalchemy import case
import json


class MessageRepository:
    def __init__(self, db):
        self.db = db

    def create(self, message: Message, *, db_session=None) -> Message:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(message, db_session=managed_session)

        model = MessageModel(**message.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return Message.model_validate(model)

    def get(self, message_id: str, *, db_session=None) -> Message | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(message_id, db_session=managed_session)

        model = db_session.query(MessageModel).filter_by(id=message_id).first()
        return Message.model_validate(model) if model else None

    def list_by_session(self, session_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(MessageModel.session_id == session_id)
                .order_by(
                    case((TurnModel.turn_index.is_(None), 1), else_=0).asc(),
                    TurnModel.turn_index.asc(),
                    MessageModel.turn_message_index.asc(),
                    MessageModel.created_at.asc(),
                )
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def list_recent_by_session(self, session_id: str, *, limit: int = 200) -> list[Message]:
        """
        Return the most recent session messages with a bounded query.

        Messages are returned in chronological order (oldest -> newest) within the selected window.
        """
        resolved_limit = 0
        try:
            resolved_limit = int(limit)
        except (TypeError, ValueError):
            resolved_limit = 0
        if resolved_limit <= 0:
            return []

        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(MessageModel.session_id == session_id)
                .order_by(
                    case((TurnModel.turn_index.is_(None), 1), else_=0).asc(),
                    TurnModel.turn_index.desc(),
                    MessageModel.turn_message_index.desc(),
                    MessageModel.created_at.desc(),
                )
                .limit(resolved_limit)
                .all()
            )
            # Convert back to chronological order for downstream logic.
            return [Message.model_validate(model) for model in reversed(models)]

    def list_by_turn(self, turn_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(turn_id=turn_id)
                .order_by(MessageModel.turn_message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def list_by_run(self, run_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(run_id=run_id)
                .order_by(MessageModel.turn_message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def update(self, message: Message, *, db_session=None) -> Message:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(message, db_session=managed_session)

        model = db_session.query(MessageModel).filter_by(id=message.id).first()
        if model is None:
            raise ValueError("消息不存在")

        model.stream_state = message.stream_state.value
        model.content_text = message.content_text
        model.payload_json = message.payload_json
        model.updated_at = message.updated_at
        model.completed_at = message.completed_at
        db_session.flush()
        db_session.refresh(model)
        return Message.model_validate(model)

    def next_turn_message_index(self, turn_id: str, *, db_session=None) -> int:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.next_turn_message_index(turn_id, db_session=managed_session)

        current = (
            db_session.query(MessageModel.turn_message_index)
            .filter_by(turn_id=turn_id)
            .order_by(MessageModel.turn_message_index.desc())
            .limit(1)
            .scalar()
        ) or 0
        return current + 1

    def from_payload(self, *, session_id: str, payload: dict) -> Message:
        def _coerce_payload_json(value: object) -> dict:
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except (TypeError, ValueError):
                    return {}
                return parsed if isinstance(parsed, dict) else {}
            return {}

        message_type = MessageType(payload["message_type"])
        if message_type == MessageType.USER_MESSAGE:
            stream_state = StreamState.COMPLETED
        else:
            stream_state = StreamState.IDLE

        return Message(
            id=payload["message_id"],
            session_id=session_id,
            turn_id=payload["turn_id"],
            run_id=payload.get("run_id"),
            turn_message_index=payload["turn_message_index"],
            role=payload["role"],
            message_type=message_type,
            stream_state=stream_state,
            display_mode=payload["display_mode"],
            content_text=payload.get("content_text", ""),
            payload_json=_coerce_payload_json(payload.get("payload_json")),
        )
