"""会话事件投影服务：将写入事件日志（ConversationEvent）的领域事件，逐条应用（apply）为
Session/Turn/Run/Message 等读模型表的状态变更，并同步更新消息检索索引。是事件溯源模式中
"事件 -> 读模型" 的投影层，事件本身的落盘由上游 conversation_service 负责。"""

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
from app.storage.repositories.message_repo import MessageRepository
from app.storage.repositories.message_search_document_repo import MessageSearchDocumentRepository
from app.storage.repositories.run_repo import RunRepository
from app.storage.repositories.session_repo import SessionRepository
from app.storage.repositories.turn_repo import TurnRepository


class ConversationProjection:
    """会话事件投影器：按事件类型分派到不同读模型表的写入逻辑，维护 Run 状态机的合法转换。"""

    TERMINAL_RUN_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        turn_repo: TurnRepository,
        run_repo: RunRepository,
        message_repo: MessageRepository,
        message_search_repo: MessageSearchDocumentRepository | None = None,
    ):
        """初始化投影器，注入各读模型的仓储依赖。
        输入：session_repo/turn_repo/run_repo/message_repo（对应读模型的仓储实例）、
              message_search_repo（消息检索索引仓储，可选，为 None 时跳过检索索引维护）
        """
        self.session_repo = session_repo
        self.turn_repo = turn_repo
        self.run_repo = run_repo
        self.message_repo = message_repo
        self.message_search_repo = message_search_repo

    def apply(self, session_id: str, event: ConversationEvent, *, db_session=None) -> None:
        """将单条会话事件应用到读模型（核心入口方法）。
        输入：session_id（会话 ID）、event（待投影的领域事件，含 event_type 和 payload_json）、
              db_session（可选的数据库会话，用于事务内批量投影）
        逻辑：按 event.event_type 分派：
          - TURN_CREATED：新建 Turn，并将其设为会话的 active_turn_id；
          - MESSAGE_CREATED：新建 Message，并同步写入检索索引；
          - RUN_CREATED：新建 Run，并将所属 Turn 置为 RUNNING、记录 active_run_id；
          - RUN_STARTED：Run 状态迁移为 RUNNING，记录开始时间；
          - RUN_WAITING_FOR_APPROVAL / RUN_RESUMING：Run 非终态状态迁移；
          - MESSAGE_CONTENT_COMMITTED / MESSAGE_PAYLOAD_UPDATED / MESSAGE_COMPLETED / MESSAGE_FAILED：
            更新消息内容/负载/流式状态，并同步刷新检索索引；
          - RUN_COMPLETED / RUN_FAILED / RUN_CANCELLED：Run 终态迁移，级联更新 Turn 和 Session；
          - SYSTEM_NOTICE_EMITTED：写入一条系统提示消息。
        输出：无（直接落库）
        异常：ValueError（会话不存在，或 Run/Turn/Message 状态非法）
        """
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
                self._validate_run_transition(run.status, RunStatus.RUNNING)
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
        """处理 Run 的非终态状态迁移（等待审批 / 恢复运行）。
        输入：event（RUN_WAITING_FOR_APPROVAL 或 RUN_RESUMING 事件）、db_session
        输出：无
        异常：ValueError（Run 不存在，或状态转换非法）
        """
        run = self._get_run_or_raise(event.run_id, db_session=db_session)
        next_status = {
            EventType.RUN_WAITING_FOR_APPROVAL: RunStatus.WAITING_FOR_APPROVAL,
            EventType.RUN_RESUMING: RunStatus.RESUMING,
        }[event.event_type]
        self._validate_run_transition(run.status, next_status)
        self.run_repo.update(
            run.model_copy(update={"status": next_status}),
            db_session=db_session,
        )

    def _apply_run_terminal_event(
        self, *, session_id: str, event: ConversationEvent, db_session=None
    ) -> None:
        """处理 Run 的终态事件（完成/失败/取消），级联更新 Run -> Turn -> Session。
        输入：session_id、event（RUN_COMPLETED/RUN_FAILED/RUN_CANCELLED 事件）、db_session
        逻辑：
          1. Run 状态迁移到对应终态，记录完成时间和错误信息；
          2. 所属 Turn 同步迁移到对应终态，清空 active_run_id；
          3. 所属 Session 清空 active_turn_id（表示当前无进行中的轮次）。
        输出：无
        异常：ValueError（Run/Turn/Session 不存在，或状态转换非法）
        """
        run = self._get_run_or_raise(event.run_id, db_session=db_session)
        payload = event.payload_json
        next_status = {
            EventType.RUN_COMPLETED: RunStatus.COMPLETED,
            EventType.RUN_FAILED: RunStatus.FAILED,
            EventType.RUN_CANCELLED: RunStatus.CANCELLED,
        }[event.event_type]
        self._validate_run_transition(run.status, next_status)
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
        """由 SYSTEM_NOTICE_EMITTED 事件构建一条系统提示类型的 Message 对象。
        输入：session_id、event（含 message_id/turn_id/notice_code 等信息的事件）
        输出：待写入的 Message 对象（message_type=SYSTEM_NOTICE，直接标记为已完成）
        """
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
        """按 ID 查询 Run，不存在（或 run_id 为 None）则抛异常。
        输入：run_id、db_session
        输出：Run 对象
        异常：ValueError（运行不存在）
        """
        if run_id is None:
            raise ValueError("运行不存在")
        run = self.run_repo.get(run_id, db_session=db_session)
        if run is None:
            raise ValueError("运行不存在")
        return run

    def _get_turn_or_raise(self, turn_id: str, *, db_session=None) -> Turn:
        """按 ID 查询 Turn，不存在则抛异常。
        输入：turn_id、db_session
        输出：Turn 对象
        异常：ValueError（轮次不存在）
        """
        turn = self.turn_repo.get(turn_id, db_session=db_session)
        if turn is None:
            raise ValueError("轮次不存在")
        return turn

    def _get_message_or_raise(self, message_id: str | None, *, db_session=None) -> Message:
        """按 ID 查询 Message，不存在（或 message_id 为 None）则抛异常。
        输入：message_id、db_session
        输出：Message 对象
        异常：ValueError（消息不存在）
        """
        if message_id is None:
            raise ValueError("消息不存在")
        message = self.message_repo.get(message_id, db_session=db_session)
        if message is None:
            raise ValueError("消息不存在")
        return message

    def _validate_run_transition(self, current: RunStatus, next_status: RunStatus) -> None:
        """校验 Run 状态转换是否合法：终态一旦到达不允许再迁移到其他状态（相同状态视为幂等，放行）。
        输入：current（当前状态）、next_status（目标状态）
        输出：无
        异常：ValueError（试图从终态迁出）
        """
        if current == next_status:
            return
        if current in self.TERMINAL_RUN_STATUSES:
            raise ValueError(f"非法 Run 状态转换: 终态 {current.value} → {next_status.value}")

    def _upsert_search_document(self, message: Message, turn: Turn, *, db_session=None) -> None:
        """将消息内容同步到检索索引（供全文检索/召回使用）。
        输入：message（最新消息状态）、turn（消息所属轮次，用于写入 turn_index）、db_session
        逻辑：未配置检索仓储或消息被标记为"不参与召回"时跳过；否则用最新内容 upsert 索引文档
        输出：无
        """
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
        """将 ISO 格式字符串解析为 datetime，空值返回 None。
        输入：raw（ISO 8601 格式字符串或 None）
        输出：datetime 对象或 None
        """
        if not raw:
            return None
        return datetime.fromisoformat(raw)
