from contextlib import contextmanager
from datetime import datetime, timedelta
from threading import Lock, RLock

from app.errors import NotFoundValueError
from app.ids import new_event_id, new_message_id, new_run_id, new_turn_id
from app.llm.base import MessageRole
from app.models.conversation import (
    ConversationEvent,
    EventType,
    Message,
    MessageType,
    Run,
    RunStatus,
    Turn,
    TurnStatus,
)
from app.models.conversation_snapshot import ConversationSnapshot, StartTurnResult
from app.storage.database import db as default_db
from app.storage.repositories.conversation_event_repo import ConversationEventRepository
from app.storage.repositories.message_repo import MessageRepository
from app.storage.repositories.message_search_document_repo import MessageSearchDocumentRepository
from app.storage.repositories.run_repo import RunRepository
from app.storage.repositories.session_repo import SessionRepository
from app.storage.repositories.turn_repo import TurnRepository

from .conversation_projection import ConversationProjection


class ConversationService:
    def __init__(
        self,
        *,
        db=default_db,
        session_repo: SessionRepository | None = None,
        turn_repo: TurnRepository | None = None,
        run_repo: RunRepository | None = None,
        message_repo: MessageRepository | None = None,
        message_search_repo: MessageSearchDocumentRepository | None = None,
        event_repo: ConversationEventRepository | None = None,
    ):
        self.db = db
        self.session_repo = session_repo or SessionRepository(db)
        self.turn_repo = turn_repo or TurnRepository(db)
        self.run_repo = run_repo or RunRepository(db)
        self.message_repo = message_repo or MessageRepository(db)
        self.message_search_repo = message_search_repo or MessageSearchDocumentRepository(db)
        self.event_repo = event_repo or ConversationEventRepository(db)
        self.projection = ConversationProjection(
            session_repo=self.session_repo,
            turn_repo=self.turn_repo,
            run_repo=self.run_repo,
            message_repo=self.message_repo,
            message_search_repo=self.message_search_repo,
        )
        self._session_locks_guard = Lock()
        self._session_write_locks: dict[str, RLock] = {}

    def append_events(
        self, session_id: str, events: list[ConversationEvent]
    ) -> list[ConversationEvent]:
        with self.acquire_session_write_lock(session_id):
            return self.append_events_locked(session_id, events)

    def append_events_locked(
        self, session_id: str, events: list[ConversationEvent]
    ) -> list[ConversationEvent]:
        if not events:
            return []

        if any(event.session_id != session_id for event in events):
            raise ValueError("事件会话 ID 不匹配")

        with self.db.get_session() as db_session:
            session = self.session_repo.get(session_id, db_session=db_session)
            if session is None:
                raise NotFoundValueError("会话不存在")

            persisted = self.event_repo.append_many(
                events,
                db_session=db_session,
                start_seq=session.last_event_seq + 1,
            )
            for persisted_event in persisted:
                self.projection.apply(session_id, persisted_event, db_session=db_session)

            latest_session = self.session_repo.get(session_id, db_session=db_session)
            if latest_session is None:
                raise NotFoundValueError("会话不存在")

            self.session_repo.update(
                latest_session.model_copy(update={"last_event_seq": persisted[-1].seq}),
                db_session=db_session,
            )
            return persisted

    def _get_session_write_lock(self, session_id: str) -> RLock:
        with self._session_locks_guard:
            lock = self._session_write_locks.get(session_id)
            if lock is None:
                lock = RLock()
                self._session_write_locks[session_id] = lock
            return lock

    @contextmanager
    def acquire_session_write_lock(self, session_id: str):
        lock = self._get_session_write_lock(session_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def get_snapshot(self, session_id: str, *, limit: int = 0, before: str | None = None) -> ConversationSnapshot:
        session = self.session_repo.get(session_id)
        if session is None:
            raise NotFoundValueError("会话不存在")

        if limit <= 0:
            return ConversationSnapshot(
                session=session,
                turns=self.turn_repo.list_by_session(session_id),
                runs=self.run_repo.list_by_session(session_id),
                messages=self.message_repo.list_by_session(session_id),
                has_more=False,
            )

        if before is not None:
            messages = self.message_repo.list_by_session_before(session_id, before, limit)
        else:
            messages = self.message_repo.list_by_session_latest(session_id, limit)

        total_count = self.message_repo.count_by_session(session_id)
        has_more = total_count > len(messages)

        turn_ids = list(dict.fromkeys(m.turn_id for m in messages))
        turns = self.turn_repo.list_by_ids(turn_ids) if turn_ids else []
        runs = self.run_repo.list_by_turn_ids(turn_ids) if turn_ids else []

        return ConversationSnapshot(
            session=session,
            turns=turns,
            runs=runs,
            messages=messages,
            has_more=has_more,
        )

    def list_events_after(self, session_id: str, after_seq: int) -> list[ConversationEvent]:
        return self.event_repo.list_after_seq(session_id, after_seq)

    def requires_resync(self, session_id: str, after_seq: int) -> bool:
        session = self.session_repo.get(session_id)
        if session is None:
            raise NotFoundValueError("会话不存在")

        first_seq = self.event_repo.first_seq(session_id)
        if first_seq is None:
            return False
        return after_seq < first_seq - 1 and after_seq < session.last_event_seq

    def cleanup_events(
        self,
        *,
        now: datetime | None = None,
        completed_retention: timedelta = timedelta(hours=1),
        failed_retention: timedelta = timedelta(days=7),
    ) -> int:
        current_time = now or datetime.now()
        completed_cutoff = current_time - completed_retention
        failed_cutoff = current_time - failed_retention

        completed_turns = self.turn_repo.list_terminal_before(
            [TurnStatus.COMPLETED.value],
            completed_cutoff,
        )
        failed_turns = self.turn_repo.list_terminal_before(
            [TurnStatus.FAILED.value, TurnStatus.CANCELLED.value],
            failed_cutoff,
        )
        turn_ids = list(dict.fromkeys([turn.id for turn in completed_turns + failed_turns]))
        return self.event_repo.delete_by_turn_ids(turn_ids)

    def start_turn(
        self,
        *,
        session_id: str,
        content: str,
        provider_id: str,
        model_id: str,
        workspace_ref: str | None,
    ) -> StartTurnResult:
        with self.acquire_session_write_lock(session_id):
            session = self.session_repo.get(session_id)
            if session is None:
                raise NotFoundValueError("会话不存在")
            if session.active_turn_id is not None:
                raise ValueError("会话已有活跃轮次，不能重复创建")

            turn_id = new_turn_id()
            run_id = new_run_id()
            user_message_id = new_message_id()
            next_turn_index = self.turn_repo.next_turn_index(session_id)

            self.append_events_locked(
                session_id,
                [
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type=EventType.TURN_CREATED,
                        payload_json={
                            "turn_id": turn_id,
                            "turn_index": next_turn_index,
                            "root_message_id": user_message_id,
                        },
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        message_id=user_message_id,
                        event_type=EventType.MESSAGE_CREATED,
                        payload_json={
                            "message_id": user_message_id,
                            "turn_id": turn_id,
                            "run_id": None,
                            "role": MessageRole.USER,
                            "message_type": "user_message",
                            "turn_message_index": 1,
                            "display_mode": "default",
                            "content_text": content,
                            "payload_json": {},
                        },
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        event_type=EventType.RUN_CREATED,
                        payload_json={
                            "run_id": run_id,
                            "turn_id": turn_id,
                            "attempt_index": 1,
                            "provider_id": provider_id,
                            "model_id": model_id,
                            "workspace_ref": workspace_ref,
                        },
                    ),
                ],
            )

            turn = self.turn_repo.get(turn_id)
            run = self.run_repo.get(run_id)
            user_message = self.message_repo.get(user_message_id)
            if turn is None or run is None or user_message is None:
                raise ValueError("会话事件投影失败")

            return StartTurnResult(turn=turn, run=run, user_message=user_message)

    def cancel_run(self, run_id: str):
        run = self.run_repo.get(run_id)
        if run is None:
            raise NotFoundValueError("运行不存在")

        with self.acquire_session_write_lock(run.session_id):
            latest_run = self.run_repo.get(run_id)
            if latest_run is None:
                raise NotFoundValueError("运行不存在")
            if latest_run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return latest_run

            turn = self.turn_repo.get(latest_run.turn_id)
            if turn is None:
                raise NotFoundValueError("轮次不存在")

            notice_message_id = new_message_id()
            self.append_events_locked(
                latest_run.session_id,
                [
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=latest_run.session_id,
                        turn_id=latest_run.turn_id,
                        run_id=latest_run.id,
                        event_type=EventType.RUN_CANCELLED,
                        payload_json={
                            "run_id": latest_run.id,
                            "finished_at": datetime.now().isoformat(),
                        },
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=latest_run.session_id,
                        turn_id=turn.id,
                        run_id=latest_run.id,
                        message_id=notice_message_id,
                        event_type=EventType.SYSTEM_NOTICE_EMITTED,
                        payload_json={
                            "message_id": notice_message_id,
                            "turn_id": turn.id,
                            "turn_message_index": self.message_repo.next_turn_message_index(
                                turn.id
                            ),
                            "notice_code": "run_cancelled",
                            "content_text": "本次执行已取消",
                            "related_run_id": latest_run.id,
                            "retryable": True,
                        },
                    ),
                ],
            )

            cancelled = self.run_repo.get(run_id)
            if cancelled is None:
                raise NotFoundValueError("运行不存在")
            return cancelled

    def truncate_after_message(
        self,
        *,
        session_id: str,
        message_id: str,
        keep_turn: bool = False,
    ) -> tuple[list[str], str | None]:
        message = self.message_repo.get(message_id)
        if message is None:
            raise NotFoundValueError("消息不存在")
        if message.session_id != session_id:
            raise ValueError("消息不属于当前会话")

        turn = self.turn_repo.get(message.turn_id)
        if turn is None:
            raise NotFoundValueError("轮次不存在")

        surviving_user_content: str | None = None
        deleted_turn_ids: list[str] = []

        if keep_turn:
            user_msg = self.message_repo.get_user_message_by_turn(turn.id)
            surviving_user_content = user_msg.content_text if user_msg else None

            later_turn_ids = [
                t.id for t in self.turn_repo.list_by_session(session_id)
                if t.turn_index > turn.turn_index
            ]

            if later_turn_ids:
                self.message_search_repo.delete_by_turn_ids(later_turn_ids)
                self.message_repo.delete_by_turn_ids(later_turn_ids)
                self.run_repo.delete_by_turn_ids(later_turn_ids)
                self.event_repo.delete_by_turn_ids(later_turn_ids)
                self.turn_repo.delete_by_session_after_index(session_id, turn.turn_index + 1)
                deleted_turn_ids.extend(later_turn_ids)

            self.message_search_repo.delete_by_turn_ids([turn.id])
            self.message_repo.delete_by_turn_ids([turn.id])
            self.run_repo.delete_by_turn_ids([turn.id])
            self.event_repo.delete_by_turn_ids([turn.id])
            self.turn_repo.delete_by_session_after_index(session_id, turn.turn_index)
            deleted_turn_ids.append(turn.id)
        else:
            later_or_equal_turn_ids = [
                t.id for t in self.turn_repo.list_by_session(session_id)
                if t.turn_index >= turn.turn_index
            ]

            if later_or_equal_turn_ids:
                self.message_search_repo.delete_by_turn_ids(later_or_equal_turn_ids)
                self.message_repo.delete_by_turn_ids(later_or_equal_turn_ids)
                self.run_repo.delete_by_turn_ids(later_or_equal_turn_ids)
                self.event_repo.delete_by_turn_ids(later_or_equal_turn_ids)
                self.turn_repo.delete_by_session_after_index(session_id, turn.turn_index)
                deleted_turn_ids.extend(later_or_equal_turn_ids)

        session = self.session_repo.get(session_id)
        if session and session.active_turn_id in deleted_turn_ids:
            self.session_repo.update(
                session.model_copy(update={"active_turn_id": None})
            )

        remaining_max_seq = self.event_repo.max_seq(session_id) or 0
        latest_session = self.session_repo.get(session_id)
        if latest_session:
            self.session_repo.update(
                latest_session.model_copy(update={"last_event_seq": remaining_max_seq})
            )

        return deleted_turn_ids, surviving_user_content

    def edit_and_rerun(
        self,
        *,
        session_id: str,
        message_id: str,
        new_content: str | None,
        provider_id: str,
        model_id: str,
        workspace_ref: str | None,
    ) -> StartTurnResult:
        with self.acquire_session_write_lock(session_id):
            session = self.session_repo.get(session_id)
            if session is None:
                raise NotFoundValueError("会话不存在")

            message = self.message_repo.get(message_id)
            if message is None:
                raise NotFoundValueError("消息不存在")
            if message.session_id != session_id:
                raise ValueError("消息不属于当前会话")

            is_user_message = message.message_type == MessageType.USER_MESSAGE

            if is_user_message:
                keep_turn = False
                content = new_content if new_content else message.content_text
            else:
                keep_turn = True
                content = new_content

            deleted_turn_ids, surviving_user_content = self.truncate_after_message(
                session_id=session_id,
                message_id=message_id,
                keep_turn=keep_turn,
            )

            if not content and surviving_user_content:
                content = surviving_user_content

            if not content:
                raise ValueError("无法确定重新运行的内容")

            truncated_event = ConversationEvent(
                id=new_event_id(),
                session_id=session_id,
                event_type=EventType.MESSAGES_TRUNCATED,
                payload_json={
                    "message_id": message_id,
                    "deleted_turn_ids": deleted_turn_ids,
                    "is_edit": is_user_message,
                    "is_regenerate": not is_user_message,
                },
            )
            self.append_events_locked(session_id, [truncated_event])
            print(f"new content: {content}")

            return self.start_turn(
                session_id=session_id,
                content=content,
                provider_id=provider_id,
                model_id=model_id,
                workspace_ref=workspace_ref,
            )

    def get_run(self, run_id: str) -> "Run | None":
        """Get a run by ID."""
        return self.run_repo.get(run_id)

    def list_turn_messages(self, turn_id: str) -> "list[Message]":
        """List all messages for a turn."""
        return self.message_repo.list_by_turn(turn_id)

    def next_message_index(self, turn_id: str) -> int:
        """Get the next message index for a turn."""
        return self.message_repo.next_turn_message_index(turn_id)

    def get_message(self, message_id: str) -> "Message | None":
        """Get a message by ID."""
        return self.message_repo.get(message_id)

    def get_turn(self, turn_id: str) -> Turn | None:
        """Get a turn by ID."""
        return self.turn_repo.get(turn_id)

    def get_latest_continuation_artifact(self, session_id: str, *, db_session=None) -> Message | None:
        """Get the most recent continuation artifact for a session."""
        return self.message_repo.get_latest_continuation_artifact(session_id, db_session=db_session)

    def list_recent_seed_candidates(self, session_id: str, **kwargs) -> list[Message]:
        """Return recent messages suitable for context seeding."""
        return self.message_repo.list_recent_seed_candidates(session_id, **kwargs)



conversation_service = ConversationService()
