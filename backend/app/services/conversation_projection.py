from datetime import datetime

from app.llm.base import MessageRole
from app.memory.message_normalizer import normalize_message_text
from app.models.conversation import (
    ConversationEvent,
    EventType,
    Message,
    MessageType,
    Run,
    RunStatus,
    StreamState,
    Turn,
    TurnStatus,
)


class ConversationProjection:
    def __init__(
        self, *, session_repo, turn_repo, run_repo, message_repo, message_search_repo=None
    ):
        self.session_repo = session_repo
        self.turn_repo = turn_repo
        self.run_repo = run_repo
        self.message_repo = message_repo
        self.message_search_repo = message_search_repo

    def apply(self, session_id: str, event: ConversationEvent, *, db_session=None) -> None:
        session = self.session_repo.get(session_id, db_session=db_session)
        if session is None:
            raise ValueError("会话不存在")

        payload = event.payload_json

        match event.event_type:
            case EventType.TURN_CREATED:
                self.turn_repo.create(
                    Turn(
                        id=payload["turn_id"],
                        session_id=session_id,
                        turn_index=payload["turn_index"],
                        root_message_id=payload["root_message_id"],
                        status=TurnStatus.CREATED,
                    ),
                    db_session=db_session,
                )
                self.session_repo.update(
                    session.model_copy(update={"active_turn_id": payload["turn_id"]}),
                    db_session=db_session,
                )

            case EventType.MESSAGE_CREATED:
                message = self.message_repo.create(
                    self.message_repo.from_payload(session_id=session_id, payload=payload),
                    db_session=db_session,
                )
                turn = self._get_turn_or_raise(message.turn_id, db_session=db_session)
                self._upsert_search_document(message, turn, db_session=db_session)

            case EventType.RUN_CREATED:
                self.run_repo.create(
                    Run(
                        id=payload["run_id"],
                        session_id=session_id,
                        turn_id=payload["turn_id"],
                        attempt_index=payload["attempt_index"],
                        status=RunStatus.CREATED,
                        provider_id=payload.get("provider_id"),
                        model_id=payload.get("model_id"),
                        workspace_ref=payload.get("workspace_ref"),
                    ),
                    db_session=db_session,
                )
                turn = self._get_turn_or_raise(payload["turn_id"], db_session=db_session)
                self.turn_repo.update(
                    turn.model_copy(
                        update={
                            "status": TurnStatus.RUNNING,
                            "active_run_id": payload["run_id"],
                            "updated_at": datetime.now(),
                        }
                    ),
                    db_session=db_session,
                )

            case EventType.RUN_STARTED:
                run = self._get_run_or_raise(event.run_id, db_session=db_session)
                self.run_repo.update(
                    run.model_copy(
                        update={
                            "status": RunStatus.RUNNING,
                            "started_at": self._parse_datetime(payload.get("started_at"))
                            or datetime.now(),
                        }
                    ),
                    db_session=db_session,
                )

            case EventType.RUN_WAITING_FOR_APPROVAL | EventType.RUN_RESUMING:
                self._apply_run_nonterminal_status(event=event, db_session=db_session)

            case EventType.MESSAGE_CONTENT_COMMITTED:
                message = self._get_message_or_raise(event.message_id, db_session=db_session)
                updated = self.message_repo.update(
                    message.model_copy(
                        update={
                            "content_text": str(payload.get("content_text", "")),
                            "stream_state": StreamState.STREAMING,
                            "updated_at": datetime.now(),
                        }
                    ),
                    db_session=db_session,
                )
                turn = self._get_turn_or_raise(updated.turn_id, db_session=db_session)
                self._upsert_search_document(updated, turn, db_session=db_session)

            case EventType.MESSAGE_PAYLOAD_UPDATED:
                message = self._get_message_or_raise(event.message_id, db_session=db_session)
                next_payload = dict(message.payload_json)
                next_payload.update(payload.get("payload_json", {}))
                updated = self.message_repo.update(
                    message.model_copy(
                        update={"payload_json": next_payload, "updated_at": datetime.now()}
                    ),
                    db_session=db_session,
                )
                turn = self._get_turn_or_raise(updated.turn_id, db_session=db_session)
                self._upsert_search_document(updated, turn, db_session=db_session)

            case EventType.MESSAGE_COMPLETED:
                message = self._get_message_or_raise(event.message_id, db_session=db_session)
                updated = self.message_repo.update(
                    message.model_copy(
                        update={
                            "stream_state": StreamState.COMPLETED,
                            "completed_at": self._parse_datetime(payload.get("completed_at"))
                            or datetime.now(),
                            "updated_at": datetime.now(),
                        }
                    ),
                    db_session=db_session,
                )
                turn = self._get_turn_or_raise(updated.turn_id, db_session=db_session)
                self._upsert_search_document(updated, turn, db_session=db_session)

            case EventType.MESSAGE_FAILED:
                message = self._get_message_or_raise(event.message_id, db_session=db_session)
                next_payload = dict(message.payload_json)
                next_payload.update(
                    {
                        "error_code": payload.get("error_code"),
                        "error_message": payload.get("error_message"),
                    }
                )
                updated = self.message_repo.update(
                    message.model_copy(
                        update={
                            "stream_state": StreamState.FAILED,
                            "payload_json": next_payload,
                            "updated_at": datetime.now(),
                        }
                    ),
                    db_session=db_session,
                )
                turn = self._get_turn_or_raise(updated.turn_id, db_session=db_session)
                self._upsert_search_document(updated, turn, db_session=db_session)

            case EventType.RUN_COMPLETED | EventType.RUN_FAILED | EventType.RUN_CANCELLED:
                self._apply_run_terminal_event(
                    session_id=session_id,
                    event=event,
                    db_session=db_session,
                )

            case EventType.SYSTEM_NOTICE_EMITTED:
                message = self.message_repo.create(
                    self._notice_message_from_event(session_id=session_id, event=event),
                    db_session=db_session,
                )
                turn = self._get_turn_or_raise(message.turn_id, db_session=db_session)
                self._upsert_search_document(message, turn, db_session=db_session)

    def _apply_run_nonterminal_status(
        self, *, event: ConversationEvent, db_session=None
    ) -> None:
        run = self._get_run_or_raise(event.run_id, db_session=db_session)
        next_status = {
            EventType.RUN_WAITING_FOR_APPROVAL: RunStatus.WAITING_FOR_APPROVAL,
            EventType.RUN_RESUMING: RunStatus.RESUMING,
        }[event.event_type]
        self.run_repo.update(
            run.model_copy(update={"status": next_status}),
            db_session=db_session,
        )

    def _apply_run_terminal_event(
        self, *, session_id: str, event: ConversationEvent, db_session=None
    ) -> None:
        run = self._get_run_or_raise(event.run_id, db_session=db_session)
        payload = event.payload_json
        next_status = {
            EventType.RUN_COMPLETED: RunStatus.COMPLETED,
            EventType.RUN_FAILED: RunStatus.FAILED,
            EventType.RUN_CANCELLED: RunStatus.CANCELLED,
        }[event.event_type]
        finished_at = self._parse_datetime(payload.get("finished_at")) or datetime.now()

        self.run_repo.update(
            run.model_copy(
                update={
                    "status": next_status,
                    "finished_at": finished_at,
                    "error_code": payload.get("error_code"),
                    "error_message": payload.get("error_message"),
                }
            ),
            db_session=db_session,
        )

        turn = self._get_turn_or_raise(run.turn_id, db_session=db_session)
        self.turn_repo.update(
            turn.model_copy(
                update={
                    "status": {
                        RunStatus.COMPLETED: TurnStatus.COMPLETED,
                        RunStatus.FAILED: TurnStatus.FAILED,
                        RunStatus.CANCELLED: TurnStatus.CANCELLED,
                    }[next_status],
                    "active_run_id": None,
                    "completed_at": finished_at,
                    "updated_at": datetime.now(),
                }
            ),
            db_session=db_session,
        )

        session = self.session_repo.get(session_id, db_session=db_session)
        if session is None:
            raise ValueError("会话不存在")
        self.session_repo.update(
            session.model_copy(update={"active_turn_id": None}),
            db_session=db_session,
        )

    def _notice_message_from_event(self, *, session_id: str, event: ConversationEvent) -> Message:
        payload = event.payload_json
        return Message(
            id=payload["message_id"],
            session_id=session_id,
            turn_id=payload["turn_id"],
            run_id=payload.get("related_run_id"),
            turn_message_index=payload["turn_message_index"],
            role=payload.get("role", MessageRole.SYSTEM),
            message_type=MessageType.SYSTEM_NOTICE,
            stream_state=StreamState.COMPLETED,
            display_mode=payload.get("display_mode", "default"),
            content_text=payload.get("content_text", ""),
            payload_json={
                "notice_code": payload.get("notice_code"),
                "related_run_id": payload.get("related_run_id"),
                "retryable": payload.get("retryable", False),
            },
            completed_at=datetime.now(),
        )

    def _get_run_or_raise(self, run_id: str | None, *, db_session=None) -> Run:
        if run_id is None:
            raise ValueError("运行不存在")
        run = self.run_repo.get(run_id, db_session=db_session)
        if run is None:
            raise ValueError("运行不存在")
        return run

    def _get_turn_or_raise(self, turn_id: str, *, db_session=None) -> Turn:
        turn = self.turn_repo.get(turn_id, db_session=db_session)
        if turn is None:
            raise ValueError("轮次不存在")
        return turn

    def _get_message_or_raise(self, message_id: str | None, *, db_session=None) -> Message:
        if message_id is None:
            raise ValueError("消息不存在")
        message = self.message_repo.get(message_id, db_session=db_session)
        if message is None:
            raise ValueError("消息不存在")
        return message

    def _upsert_search_document(self, message: Message, turn: Turn, *, db_session=None) -> None:
        if self.message_search_repo is None:
            return
        if message.is_excluded_from_recall():
            return
        # Derived index used for recall: keep it in sync with message content + payload updates.
        self.message_search_repo.upsert(
            message_id=message.id,
            session_id=message.session_id,
            turn_id=message.turn_id,
            run_id=message.run_id,
            role=message.role,
            message_type=message.message_type.value,
            turn_index=turn.turn_index,
            turn_message_index=message.turn_message_index,
            search_text=normalize_message_text(message),
            db_session=db_session,
        )

    def _parse_datetime(self, raw: str | None) -> datetime | None:
        if not raw:
            return None
        return datetime.fromisoformat(raw)
