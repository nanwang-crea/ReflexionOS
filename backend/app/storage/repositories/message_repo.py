import json

from sqlalchemy import and_, case, func, or_

from app.errors import NotFoundValueError
from app.models.conversation import Message, MessageType, StreamState
from app.storage.models import MessageModel, TurnModel

from .base_repo import BaseRepository


class MessageRepository(BaseRepository[Message]):
    def __init__(self, db):
        super().__init__(db, Message)

    def create(self, message: Message, *, db_session=None) -> Message:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(message, db_session=managed_session)

        model = MessageModel(**message.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, message_id: str, *, db_session=None) -> Message | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(message_id, db_session=managed_session)

        model = db_session.query(MessageModel).filter_by(id=message_id).first()
        return self._to_domain(model)

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
            return self._to_domain_list(models)

    def count_by_session(self, session_id: str) -> int:
        with self.db.get_session() as db_session:
            count = (
                db_session.query(func.count(MessageModel.id))
                .filter(MessageModel.session_id == session_id)
                .scalar()
            )
            return int(count or 0)

    def list_by_session_latest(self, session_id: str, limit: int) -> list[Message]:
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
                    case((TurnModel.turn_index.is_(None), 1), else_=0).desc(),
                    TurnModel.turn_index.desc(),
                    MessageModel.turn_message_index.desc(),
                    MessageModel.created_at.desc(),
                )
                .limit(limit)
                .all()
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_session_before(self, session_id: str, before_message_id: str, limit: int) -> list[Message]:
        with self.db.get_session() as db_session:
            cursor = db_session.query(MessageModel).filter_by(id=before_message_id).first()
            if cursor is None:
                return self.list_by_session_latest(session_id, limit)

            cursor_turn = db_session.query(TurnModel).filter_by(id=cursor.turn_id).first()
            cursor_turn_index = cursor_turn.turn_index if cursor_turn else 0

            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(
                    MessageModel.session_id == session_id,
                    or_(
                        TurnModel.turn_index < cursor_turn_index,
                        and_(
                            TurnModel.turn_index == cursor_turn_index,
                            MessageModel.turn_message_index < cursor.turn_message_index,
                        ),
                    ),
                )
                .order_by(
                    case((TurnModel.turn_index.is_(None), 1), else_=0).desc(),
                    TurnModel.turn_index.desc(),
                    MessageModel.turn_message_index.desc(),
                    MessageModel.created_at.desc(),
                )
                .limit(limit)
                .all()
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_turn(self, turn_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(turn_id=turn_id)
                .order_by(MessageModel.turn_message_index.asc())
                .all()
            )
            return self._to_domain_list(models)

    def update(self, message: Message, *, db_session=None) -> Message:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(message, db_session=managed_session)

        model = db_session.query(MessageModel).filter_by(id=message.id).first()
        if model is None:
            raise NotFoundValueError("消息不存在")

        model.stream_state = message.stream_state.value
        model.content_text = message.content_text
        model.payload_json = message.payload_json
        model.updated_at = message.updated_at
        model.completed_at = message.completed_at
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

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

    def list_recent_seed_candidates(
        self,
        session_id: str,
        *,
        current_turn_id: str | None = None,
        limit: int = 8,
        scan_limit: int = 200,
        max_tool_traces: int = 4,
    ) -> list[Message]:
        resolved_limit = max(0, int(limit)) if limit else 0
        resolved_scan = max(50, int(scan_limit)) if scan_limit else 200
        if resolved_limit <= 0:
            return []

        with self.db.get_session() as db_session:
            query = db_session.query(MessageModel).filter(
                MessageModel.session_id == session_id,
                MessageModel.message_type.in_(
                    [
                        MessageType.USER_MESSAGE.value,
                        MessageType.ASSISTANT_MESSAGE.value,
                    ]
                ),
                MessageModel.content_text != "",
                func.coalesce(
                    func.json_extract(MessageModel.payload_json, "$.kind"),
                    "",
                )
                != "continuation_artifact",
            )
            if current_turn_id:
                query = query.filter(MessageModel.turn_id != current_turn_id)

            models = query.order_by(MessageModel.created_at.desc()).limit(resolved_scan).all()

            text_candidates = self._to_domain_list(list(reversed(models)))[-resolved_limit:]

            tool_trace_models = (
                db_session.query(MessageModel)
                .filter(
                    MessageModel.session_id == session_id,
                    MessageModel.message_type == MessageType.TOOL_TRACE.value,
                    MessageModel.stream_state == StreamState.COMPLETED.value,
                )
            )
            if current_turn_id:
                tool_trace_models = tool_trace_models.filter(
                    MessageModel.turn_id != current_turn_id
                )
            tool_trace_models = (
                tool_trace_models.order_by(MessageModel.created_at.desc())
                .limit(max_tool_traces)
                .all()
            )
            tool_traces = list(reversed(self._to_domain_list(tool_trace_models)))

            return text_candidates + tool_traces

    def get_latest_continuation_artifact(
        self,
        session_id: str,
        *,
        db_session=None,
    ) -> Message | None:

        def _query(session):
            model = (
                session.query(MessageModel)
                .filter(
                    MessageModel.session_id == session_id,
                    MessageModel.message_type == MessageType.SYSTEM_NOTICE.value,
                    func.json_extract(MessageModel.payload_json, "$.kind")
                    == "continuation_artifact",
                    MessageModel.content_text != "",
                )
                .order_by(MessageModel.created_at.desc())
                .limit(1)
                .first()
            )
            return self._to_domain(model)

        if db_session is None:
            with self.db.get_session() as managed_session:
                return _query(managed_session)

        return _query(db_session)

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        if not turn_ids:
            return 0

        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

        deleted = (
            db_session.query(MessageModel)
            .filter(MessageModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)

    def get_user_message_by_turn(self, turn_id: str, *, db_session=None) -> Message | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get_user_message_by_turn(turn_id, db_session=managed_session)

        model = (
            db_session.query(MessageModel)
            .filter_by(turn_id=turn_id, message_type=MessageType.USER_MESSAGE.value)
            .order_by(MessageModel.turn_message_index.asc())
            .first()
        )
        return self._to_domain(model)

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
