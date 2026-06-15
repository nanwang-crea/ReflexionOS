import json
import logging

from sqlalchemy import and_, case, func, or_

from app.errors import NotFoundValueError
from app.models.conversation import Message, MessageAttachment, MessageType, StreamState
from app.storage.models import MessageModel, TurnModel

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository[Message]):
    def __init__(self, db):
        super().__init__(db, Message)

    def _to_domain(self, model) -> Message | None:
        """Override to handle attachments_json conversion"""
        if model is None:
            return None

        data = {
            "id": model.id,
            "session_id": model.session_id,
            "turn_id": model.turn_id,
            "run_id": model.run_id,
            "turn_message_index": model.turn_message_index,
            "role": model.role,
            "message_type": model.message_type,
            "stream_state": model.stream_state,
            "display_mode": model.display_mode,
            "content_text": model.content_text,
            "payload_json": model.payload_json,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
            "completed_at": model.completed_at,
        }

        # Convert attachments_json to attachments list
        if hasattr(model, "attachments_json") and model.attachments_json:
            try:
                attachments_data = json.loads(model.attachments_json)
                data["attachments"] = [MessageAttachment(**att) for att in attachments_data]
            except (json.JSONDecodeError, TypeError, ValueError):
                data["attachments"] = []
        else:
            data["attachments"] = []

        return Message(**data)

    def create(self, message: Message, *, db_session=None) -> Message:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(message, db_session=managed_session)

        data = message.model_dump()
        # Convert attachments list to JSON string for storage
        if "attachments" in data:
            attachments = data.pop("attachments")
            if attachments:
                data["attachments_json"] = json.dumps(
                    [att.model_dump() if hasattr(att, "model_dump") else att for att in attachments]
                )
            else:
                data["attachments_json"] = None

        model = MessageModel(**data)
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
                logger.warning(
                    "message page fallback to latest session_id=%s before_message_id=%s limit=%s reason=cursor_missing",
                    session_id,
                    before_message_id,
                    limit,
                )
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
            logger.info(
                "message page before session_id=%s before_message_id=%s cursor_turn_id=%s cursor_turn_index=%s cursor_message_index=%s returned_ids=%s",
                session_id,
                before_message_id,
                cursor.turn_id,
                cursor_turn_index,
                cursor.turn_message_index,
                [model.id for model in models],
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

    def list_by_turn_ids(self, session_id: str, turn_ids: list[str]) -> list[Message]:
        if not turn_ids:
            return []

        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(
                    MessageModel.session_id == session_id,
                    MessageModel.turn_id.in_(turn_ids),
                )
                .order_by(
                    TurnModel.turn_index.asc(),
                    MessageModel.turn_message_index.asc(),
                    MessageModel.created_at.asc(),
                )
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
        if message.attachments:
            model.attachments_json = json.dumps([att.model_dump() for att in message.attachments])
        else:
            model.attachments_json = None
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
        limit: int = 12,
        scan_limit: int = 200,
        max_tool_traces: int = 20,
    ) -> list[Message]:
        resolved_limit = max(0, int(limit)) if limit else 0
        resolved_scan = max(50, int(scan_limit)) if scan_limit else 200
        if resolved_limit <= 0:
            return []

        with self.db.get_session() as db_session:
            text_query = db_session.query(MessageModel).filter(
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
                text_query = text_query.filter(MessageModel.turn_id != current_turn_id)

            text_models = text_query.order_by(MessageModel.created_at.desc()).limit(resolved_scan).all()

            tool_trace_query = (
                db_session.query(MessageModel)
                .filter(
                    MessageModel.session_id == session_id,
                    MessageModel.message_type == MessageType.TOOL_TRACE.value,
                    MessageModel.stream_state == StreamState.COMPLETED.value,
                )
            )
            if current_turn_id:
                tool_trace_query = tool_trace_query.filter(
                    MessageModel.turn_id != current_turn_id
                )
            tool_trace_models = (
                tool_trace_query.order_by(MessageModel.created_at.desc())
                .limit(max_tool_traces)
                .all()
            )

            all_models = list(text_models) + list(tool_trace_models)
            all_models.sort(key=lambda m: m.created_at)
            all_models = all_models[-resolved_limit:]

            return self._to_domain_list(all_models)

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

        # 处理附件 IDs - 转换为 MessageAttachment 对象
        attachments = []
        attachment_ids = payload.get("attachment_ids", [])
        if attachment_ids:
            from pathlib import Path
            from datetime import datetime
            from app.models.conversation import MessageAttachment

            for att_id in attachment_ids:
                # 从 attachment_id 推断文件路径
                # attachment_id 格式: "att_<file_id>"
                # 文件路径格式: storage/uploads/{session_id}/{timestamp}_{file_id}.ext

                # 搜索匹配的文件
                upload_dir = Path("storage/uploads") / session_id
                if upload_dir.exists():
                    file_id = att_id.replace("att_", "")
                    matching_files = list(upload_dir.glob(f"*_{file_id}.*"))
                    if matching_files:
                        file_path = matching_files[0]
                        # 推断 MIME 类型
                        ext = file_path.suffix.lower()
                        mime_map = {
                            ".png": "image/png",
                            ".jpg": "image/jpeg",
                            ".jpeg": "image/jpeg",
                            ".gif": "image/gif",
                            ".webp": "image/webp",
                        }
                        mime_type = mime_map.get(ext, "image/png")

                        attachments.append(MessageAttachment(
                            id=att_id,
                            type="image",
                            mime_type=mime_type,
                            file_path=str(file_path),
                            file_size=file_path.stat().st_size if file_path.exists() else 0,
                            created_at=datetime.now(),
                        ))

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
            attachments=attachments,
        )
