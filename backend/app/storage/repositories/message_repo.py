from app.models.conversation import Message, MessageType, StreamState
from app.storage.models import MessageModel


class MessageRepository:
    def __init__(self, db):
        self.db = db

    def create(self, message: Message) -> Message:
        with self.db.get_session() as db_session:
            model = MessageModel(**message.model_dump())
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return Message.model_validate(model)

    def get(self, message_id: str) -> Message | None:
        with self.db.get_session() as db_session:
            model = db_session.query(MessageModel).filter_by(id=message_id).first()
            return Message.model_validate(model) if model else None

    def list_by_session(self, session_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(session_id=session_id)
                .order_by(MessageModel.created_at.asc(), MessageModel.message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def list_by_turn(self, turn_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(turn_id=turn_id)
                .order_by(MessageModel.message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def list_by_run(self, run_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(run_id=run_id)
                .order_by(MessageModel.message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def update(self, message: Message) -> Message:
        with self.db.get_session() as db_session:
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

    def next_message_index(self, turn_id: str) -> int:
        with self.db.get_session() as db_session:
            current = (
                db_session.query(MessageModel.message_index)
                .filter_by(turn_id=turn_id)
                .order_by(MessageModel.message_index.desc())
                .limit(1)
                .scalar()
            ) or 0
            return current + 1

    def from_payload(self, *, session_id: str, payload: dict) -> Message:
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
            message_index=payload["message_index"],
            role=payload["role"],
            message_type=message_type,
            stream_state=stream_state,
            display_mode=payload["display_mode"],
            content_text=payload.get("content_text", ""),
            payload_json=payload.get("payload_json", {}),
        )
