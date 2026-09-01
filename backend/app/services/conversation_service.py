"""会话对话服务：事件溯源模式下的写入侧核心服务。负责生成/追加会话事件（ConversationEvent）、
驱动 ConversationProjection 落地读模型、维护每会话写锁保证事件顺序一致，并封装"新建轮次""取消运行"
"截断重跑""编辑重新生成""重置会话"等对话领域的复合业务流程。"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from threading import Lock, RLock
import logging

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
from app.models.session import Session
from app.storage.database import db as default_db
from app.storage.repositories.conversation_event_repo import ConversationEventRepository
from app.storage.repositories.message_repo import MessageRepository
from app.storage.repositories.message_search_document_repo import MessageSearchDocumentRepository
from app.storage.repositories.run_repo import RunRepository
from app.storage.repositories.session_repo import SessionRepository
from app.storage.repositories.turn_repo import TurnRepository
from app.services.attachment_service import get_attachment_service

from .conversation_projection import ConversationProjection

logger = logging.getLogger(__name__)


class ConversationService:
    """会话对话服务：对外提供事件追加、快照读取、轮次生命周期管理等能力。"""

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
        """初始化服务，构建各仓储依赖及内部的事件投影器，并准备按会话粒度的写锁表。
        输入：db（数据库实例）、各 repo（均可选，缺省基于 db 自动构建，便于测试注入）
        """
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
        """加锁追加一批事件到指定会话（对外主入口，内部自动获取会话写锁保证顺序性）。
        输入：session_id、events（待追加的事件列表）
        输出：持久化后的事件列表（含分配好的 seq）
        """
        with self.acquire_session_write_lock(session_id):
            return self.append_events_locked(session_id, events)

    def append_events_locked(
        self, session_id: str, events: list[ConversationEvent]
    ) -> list[ConversationEvent]:
        """在已持有会话写锁的前提下追加事件（供已加锁的复合业务流程内部调用，避免重入死锁）。
        输入：session_id、events（待追加事件列表，需均属于该 session_id）
        逻辑：
          1. 校验所有事件的 session_id 与传入一致；
          2. 在同一数据库事务内：按 session.last_event_seq+1 起始分配序号并落盘事件；
          3. 逐条调用 projection.apply 将事件同步投影到读模型；
          4. 更新 session.last_event_seq 为本批次最后一条事件的 seq。
        输出：持久化后的事件列表；events 为空时直接返回空列表
        异常：ValueError（事件 session_id 不匹配）、NotFoundValueError（会话不存在）
        """
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
        """获取（不存在则创建）指定会话的可重入锁，用全局 guard 锁保护锁表本身的并发访问。
        输入：session_id
        输出：该会话专属的 RLock 实例
        """
        with self._session_locks_guard:
            lock = self._session_write_locks.get(session_id)
            if lock is None:
                lock = RLock()
                self._session_write_locks[session_id] = lock
            return lock

    @contextmanager
    def acquire_session_write_lock(self, session_id: str):
        """会话写锁的上下文管理器，确保同一会话的事件追加/复合写操作互斥执行。
        输入：session_id
        用法：with self.acquire_session_write_lock(session_id): ...
        """
        lock = self._get_session_write_lock(session_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def get_snapshot(
        self,
        session_id: str,
        *,
        limit: int = 0,
        before_turn: str | None = None,
    ) -> ConversationSnapshot:
        """获取会话的读模型快照（turns/runs/messages），支持按轮次分页向前加载历史。
        输入：session_id、limit（每页轮次数，<=0 表示不分页返回全部）、
              before_turn（游标，返回该轮次之前的历史，配合分页向前翻页使用）
        逻辑：
          - limit<=0：一次性返回该会话全部 turns 及关联的 runs/messages；
          - limit>0：多查一条（probe_limit=limit+1）探测是否还有更多历史，
            并据此计算 has_more 和下一页游标 next_before_turn_id。
        输出：ConversationSnapshot（session、turns、runs、messages、has_more、next_before_turn_id）
        异常：NotFoundValueError（会话不存在）
        """
        normalized_before_turn = before_turn or None
        session = self.session_repo.get(session_id)
        if session is None:
            raise NotFoundValueError("会话不存在")

        if limit <= 0:
            turns = self.turn_repo.list_by_session(session_id)
            turn_ids = [turn.id for turn in turns]
            return ConversationSnapshot(
                session=session,
                turns=turns,
                runs=self.run_repo.list_by_turn_ids(session_id, turn_ids),
                messages=self.message_repo.list_by_turn_ids(session_id, turn_ids),
                has_more=False,
                next_before_turn_id=None,
            )

        probe_limit = limit + 1
        if normalized_before_turn is not None:
            page_turns = self.turn_repo.list_by_session_before(
                session_id,
                normalized_before_turn,
                probe_limit,
            )
        else:
            page_turns = self.turn_repo.list_by_session_latest(session_id, probe_limit)

        has_more = len(page_turns) > limit
        if has_more:
            page_turns = page_turns[-limit:]

        turn_ids = [turn.id for turn in page_turns]
        runs = self.run_repo.list_by_turn_ids(session_id, turn_ids)
        messages = self.message_repo.list_by_turn_ids(session_id, turn_ids)

        return ConversationSnapshot(
            session=session,
            turns=page_turns,
            runs=runs,
            messages=messages,
            has_more=has_more,
            next_before_turn_id=page_turns[0].id if has_more and page_turns else None,
        )

    def list_events_after(self, session_id: str, after_seq: int) -> list[ConversationEvent]:
        """获取指定序号之后的全部事件，供前端增量同步（长轮询/重连补发）使用。
        输入：session_id、after_seq（起点序号，不含自身）
        输出：ConversationEvent 列表，按 seq 升序
        """
        return self.event_repo.list_after_seq(session_id, after_seq)

    def requires_resync(self, session_id: str, after_seq: int) -> bool:
        """判断客户端持有的事件序号是否已过旧（早于当前保留的最早事件），需要整体重新拉取快照。
        输入：session_id、after_seq（客户端已知的最新事件序号）
        逻辑：若会话当前最早保留事件的 seq 比 after_seq+1 还大，说明中间有事件被清理（cleanup_events），
              且 after_seq 落后于会话最新进度，则必须重新同步
        输出：bool，True 表示需要客户端重新拉取完整快照
        异常：NotFoundValueError（会话不存在）
        """
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
        """按保留策略批量清理已终止轮次关联的事件日志（读模型 turn/run/message 数据不受影响，仅清理事件表）。
        输入：now（基准时间，默认当前时间）、completed_retention（已完成轮次的保留时长，默认 1 小时）、
              failed_retention（失败/取消轮次的保留时长，默认 7 天，便于排查问题）
        输出：实际删除的事件数量
        """
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
        attachment_ids: list[str] | None = None,
    ) -> StartTurnResult:
        """在会话中发起一个新轮次：写入用户消息并创建首次 Run（对话主流程的起点）。
        输入：session_id、content（用户消息文本）、provider_id/model_id（本轮使用的 LLM 供应商与模型）、
              workspace_ref（工作区/项目引用，供 Agent 执行时定位代码目录）、attachment_ids（可选，附件 ID 列表）
        逻辑：
          1. 加会话写锁，校验会话存在且当前没有活跃轮次（同一会话不允许并发多轮）；
          2. 生成 turn_id/run_id/user_message_id，计算下一个 turn_index；
          3. 若带附件，通过 AttachmentService 构建附件元数据写入消息 payload；
          4. 依次追加 TURN_CREATED、MESSAGE_CREATED（用户消息）、RUN_CREATED 三个事件；
          5. 从读模型重新查出刚落地的 turn/run/user_message 返回。
        输出：StartTurnResult(turn, run, user_message)
        异常：NotFoundValueError（会话不存在）、ValueError（已有活跃轮次 / 投影后数据缺失）
        """
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

            # 构建消息 payload，包含附件信息
            message_payload = {
                "message_id": user_message_id,
                "turn_id": turn_id,
                "run_id": None,
                "role": MessageRole.USER,
                "message_type": "user_message",
                "turn_message_index": 1,
                "display_mode": "default",
                "content_text": content,
                "payload_json": {},
            }

            # 如果有附件，添加到 payload
            if attachment_ids:
                message_payload["attachment_ids"] = attachment_ids

                # 使用 AttachmentService 构建附件元数据
                attachment_service = get_attachment_service()
                attachments_data = attachment_service.build_attachments_for_message(
                    session_id,
                    attachment_ids
                )

                # 总是设置 attachments 字段
                message_payload["attachments"] = attachments_data
                logger.info(
                    f"start_turn: session={session_id}, attachment_ids={attachment_ids}, "
                    f"找到 {len(attachments_data)} 个附件"
                )
            else:
                # 没有附件时，也设置为空数组
                message_payload["attachments"] = []

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
                        payload_json=message_payload,
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
        """取消一个正在进行的 Run：写入 RUN_CANCELLED 事件并追加一条"已取消"的系统提示消息。
        输入：run_id
        逻辑：
          1. 若 Run 已处于终态（COMPLETED/FAILED/CANCELLED），直接返回当前状态（幂等）；
          2. 否则加会话写锁，追加 RUN_CANCELLED 事件（触发 Run/Turn/Session 级联状态更新）
             和 SYSTEM_NOTICE_EMITTED 事件（提示用户本次执行已取消，且标记 retryable）。
        输出：取消后的 Run 对象（终态情况下为查询到的当前状态）
        异常：NotFoundValueError（Run 或所属 Turn 不存在）
        """
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
        """删除指定消息所在轮次及其之后的所有轮次数据（用于"编辑消息重新生成"或"重新生成回答"场景）。
        输入：session_id、message_id（截断基准消息）、
              keep_turn（True=保留该消息所在轮次本身，只删除更晚的轮次，用于重新生成 AI 回复；
                         False=连同该消息所在轮次一起删除，用于编辑用户消息后重新提问）
        逻辑：
          1. 定位消息及其所属轮次；
          2. keep_turn=True：先记下该轮次原始用户消息内容（供上层复用），删除 turn_index 更大的轮次，
             再单独清空该轮次内容（消息/run/event），但轮次记录本身保留；
          3. keep_turn=False：直接删除 turn_index >= 当前轮次的所有轮次（含当前轮次本身）；
          4. 若被删除的轮次里包含会话当前 active_turn_id，清空该字段；
          5. 按剩余事件重新计算 last_event_seq 并回写 session。
          注：此方法仅做级联删除读模型数据，不写入 MESSAGES_TRUNCATED 事件，调用方（如 edit_and_rerun）
              负责在此之后自行追加该事件用于审计。
        输出：(deleted_turn_ids, surviving_user_content)
              deleted_turn_ids：被删除的轮次 id 列表；
              surviving_user_content：keep_turn=True 时保留下来的原始用户消息文本，否则为 None
        异常：NotFoundValueError（消息或轮次不存在）、ValueError（消息不属于该会话）
        """
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

    def reset_session(self, session_id: str) -> "Session":
        """清空会话历史但保留会话本身（清空历史、保留会话）。

        在写锁内重校验无活跃 run 后，真实级联删除该 session 全部
        turn/run/message/event/search，并把 active_turn_id / last_event_seq 归零。
        语义等价于把会话截断到第 0 个 turn 之前。
        """
        with self.acquire_session_write_lock(session_id):
            session = self.session_repo.get(session_id)
            if session is None:
                raise NotFoundValueError("会话不存在")

            active_run: Run | None = None
            if session.active_turn_id is not None:
                turn = self.turn_repo.get(session.active_turn_id)
                if turn is not None and turn.active_run_id is not None:
                    active_run = self.run_repo.get(turn.active_run_id)
            if active_run is not None and active_run.status in {
                RunStatus.RUNNING,
                RunStatus.WAITING_FOR_APPROVAL,
            }:
                raise ValueError("会话仍有运行中的任务，无法重置")

            turn_ids = [t.id for t in self.turn_repo.list_by_session(session_id)]
            if turn_ids:
                self.message_search_repo.delete_by_turn_ids(turn_ids)
                self.message_repo.delete_by_turn_ids(turn_ids)
                self.run_repo.delete_by_turn_ids(turn_ids)
                self.event_repo.delete_by_turn_ids(turn_ids)
                self.turn_repo.delete_by_session_after_index(session_id, 0)

            latest_session = self.session_repo.get(session_id)
            self.session_repo.update(
                latest_session.model_copy(
                    update={"active_turn_id": None, "last_event_seq": 0}
                )
            )

            cleared_session = self.session_repo.get(session_id)
            if cleared_session is None:
                raise NotFoundValueError("会话不存在")
            return cleared_session

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
        """编辑历史消息并重新发起一轮对话（覆盖"编辑用户消息重问"和"重新生成 AI 回复"两种场景）。
        输入：session_id、message_id（目标消息）、new_content（新内容，重新生成场景可为 None 沿用原文）、
              provider_id/model_id/workspace_ref（重新发起轮次使用的供应商/模型/工作区）
        逻辑：
          1. 判断目标消息类型：用户消息 -> keep_turn=False（连同该轮次一起删除，重新提问，并保留原附件）；
             其他类型（如 AI 回复）-> keep_turn=True（只删除更晚的轮次，重新生成本轮回复）；
          2. 调用 truncate_after_message 执行级联删除；
          3. 内容确实缺失时回退用 surviving_user_content；仍无内容则报错；
          4. 追加 MESSAGES_TRUNCATED 事件记录本次截断动作（用于审计/前端提示）；
          5. 调用 start_turn 以最终内容发起新一轮对话。
        输出：StartTurnResult（新轮次的 turn/run/user_message）
        异常：NotFoundValueError（会话或消息不存在）、ValueError（消息不属于该会话 / 无法确定重新运行的内容）
        """
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
                # 保留原始用户消息的附件
                original_attachment_ids = [att.id for att in message.attachments]
            else:
                keep_turn = True
                content = new_content
                original_attachment_ids = []

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

            return self.start_turn(
                session_id=session_id,
                content=content,
                provider_id=provider_id,
                model_id=model_id,
                workspace_ref=workspace_ref,
                attachment_ids=original_attachment_ids or None,
            )

    def get_run(self, run_id: str) -> "Run | None":
        """按 ID 查询 Run，不存在返回 None。"""
        return self.run_repo.get(run_id)

    def list_turn_messages(self, turn_id: str) -> "list[Message]":
        """列出指定轮次下的全部消息。"""
        return self.message_repo.list_by_turn(turn_id)

    def next_message_index(self, turn_id: str) -> int:
        """获取指定轮次下一条消息应使用的 turn_message_index（自增序号）。"""
        return self.message_repo.next_turn_message_index(turn_id)

    def get_message(self, message_id: str) -> "Message | None":
        """按 ID 查询消息，不存在返回 None。"""
        return self.message_repo.get(message_id)

    def get_turn(self, turn_id: str) -> Turn | None:
        """按 ID 查询轮次，不存在返回 None。"""
        return self.turn_repo.get(turn_id)

    def list_recent_seed_candidates(self, session_id: str, **kwargs) -> list[Message]:
        """获取适合用作上下文种子（seed）的近期消息候选列表，供发起新对话时构建上下文摘要使用。
        输入：session_id、**kwargs（透传给仓储层的筛选参数，如数量限制等）
        输出：Message 列表
        """
        return self.message_repo.list_recent_seed_candidates(session_id, **kwargs)



conversation_service = ConversationService()
