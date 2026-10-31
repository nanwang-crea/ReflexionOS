# 文件功能：会话级消息发送队列（参考 reflexion-os-studio 的 QueueService 设计）
# 文件描述：当会话已有活跃轮次（Agent 正在回复）时，用户新提交的消息进入按会话隔离的
#   FIFO 队列，待当前 Run 结束后自动按序发起下一轮；支持编辑、删除、插队（立即发送）、
#   暂停与恢复。队列只存在于进程内存中（与审批存储、执行循环同生命周期），进程重启即清空，
#   因此不参与事件溯源、不落库，其状态通过 WebSocket "conversation:queue_state" 全量快照广播。
# 核心逻辑：SessionMessageQueueManager 以 {session_id: deque[QueuedMessage]} 维护各会话队列，
#   另以 Set 维护暂停标记；出队遵循"先弹出、再发起、失败则放回队首并暂停"的语义，
#   保证同一排队项不会被重复消费，也不会在发起失败后静默丢失。
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

# 单会话队列长度上限：防止无限堆积（超限入队直接报错，由调用方转为 conversation:error）
MAX_QUEUE_SIZE_PER_SESSION = 20


@dataclass
class QueuedMessage:
    """队列中的一条待发送消息。

    provider_id/model_id 记录入队时的选择快照（仅为透传，真正解析在出队后由 start_turn 完成），
    attachment_ids 为附件 ID 列表，合法性校验延迟到出队发起时进行。
    """

    content: str
    provider_id: str | None = None
    model_id: str | None = None
    attachment_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"qmsg-{uuid4().hex[:12]}")
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """序列化为 WebSocket 广播用的字典（字段名与前端 DTO 约定一致，蛇形命名）。"""
        return {
            "id": self.id,
            "content": self.content,
            "attachment_ids": list(self.attachment_ids),
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "created_at": self.created_at,
        }


@dataclass
class MessageQueueSnapshot:
    """某会话队列的不可变状态快照，用于广播与查询。"""

    session_id: str
    paused: bool
    items: list[QueuedMessage]


class SessionMessageQueueManager:
    """按会话隔离的内存消息队列管理器。

    所有方法均为同步纯内存操作（单事件循环内调用，无需额外加锁）；
    会话删除/重置时由 AgentService.cleanup_session_security_state 调用 clear_session 清理。
    """

    def __init__(self, max_size_per_session: int = MAX_QUEUE_SIZE_PER_SESSION):
        self._queues: dict[str, deque[QueuedMessage]] = {}
        self._paused: set[str] = set()
        self._max_size = max_size_per_session

    def enqueue(
        self,
        session_id: str,
        *,
        content: str,
        provider_id: str | None = None,
        model_id: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> QueuedMessage:
        """将一条消息追加到会话队列尾部。
        异常：ValueError（队列已满，达到 max_size_per_session 上限）
        """
        queue = self._queues.get(session_id)
        if queue is None:
            queue = deque()
            self._queues[session_id] = queue
        if len(queue) >= self._max_size:
            raise ValueError(f"消息队列已满（最多 {self._max_size} 条），请先处理已排队的消息")
        item = QueuedMessage(
            content=content,
            provider_id=provider_id,
            model_id=model_id,
            attachment_ids=list(attachment_ids or []),
        )
        queue.append(item)
        return item

    def peek(self, session_id: str) -> QueuedMessage | None:
        """查看队首消息但不弹出；队列为空返回 None。"""
        queue = self._queues.get(session_id)
        if not queue:
            return None
        return queue[0]

    def pop(self, session_id: str) -> QueuedMessage | None:
        """弹出队首消息；队列为空返回 None。"""
        queue = self._queues.get(session_id)
        if not queue:
            return None
        item = queue.popleft()
        if not queue:
            # 空队列顺手回收，避免长会话累积空 deque
            self._queues.pop(session_id, None)
        return item

    def push_front(self, session_id: str, item: QueuedMessage) -> None:
        """将消息放回队首（出队后发起失败时的补偿路径，配合 pause 使用）。"""
        queue = self._queues.get(session_id)
        if queue is None:
            queue = deque()
            self._queues[session_id] = queue
        queue.appendleft(item)

    def update(self, session_id: str, queue_id: str, *, content: str) -> QueuedMessage:
        """原位编辑排队消息的文本内容。
        异常：ValueError（queue_id 不在该会话队列中）
        """
        queue = self._queues.get(session_id)
        if queue:
            for item in queue:
                if item.id == queue_id:
                    item.content = content
                    return item
        raise ValueError("排队消息不存在或已被移除")

    def remove(self, session_id: str, queue_id: str) -> bool:
        """按 id 删除一条排队消息；找不到返回 False（幂等，不报错）。"""
        queue = self._queues.get(session_id)
        if not queue:
            return False
        for item in queue:
            if item.id == queue_id:
                queue.remove(item)
                if not queue:
                    self._queues.pop(session_id, None)
                return True
        return False

    def move_to_front(self, session_id: str, queue_id: str) -> QueuedMessage:
        """将指定消息移动到队首（"立即发送"语义：下一轮出队时最先被消费）。
        异常：ValueError（queue_id 不在该会话队列中）
        """
        queue = self._queues.get(session_id)
        if not queue:
            raise ValueError("排队消息不存在或已被移除")
        for index, item in enumerate(queue):
            if item.id == queue_id:
                queue.remove(item)
                queue.appendleft(item)
                return item
        raise ValueError("排队消息不存在或已被移除")

    def pause(self, session_id: str) -> None:
        """暂停会话队列的自动出队（取消运行且队列非空时由 AgentService 调用）。"""
        self._paused.add(session_id)

    def resume(self, session_id: str) -> bool:
        """解除暂停标记；返回是否确实发生了状态变化（用于决定是否需要广播）。"""
        if session_id in self._paused:
            self._paused.discard(session_id)
            return True
        return False

    def is_paused(self, session_id: str) -> bool:
        """查询会话队列是否处于暂停状态。"""
        return session_id in self._paused

    def is_empty(self, session_id: str) -> bool:
        """查询会话队列是否为空（不存在队列或长度为 0）。"""
        queue = self._queues.get(session_id)
        return not queue

    def get_snapshot(self, session_id: str) -> MessageQueueSnapshot:
        """获取会话队列的完整快照（含暂停标记与全部排队项）。"""
        queue = self._queues.get(session_id)
        return MessageQueueSnapshot(
            session_id=session_id,
            paused=self.is_paused(session_id),
            items=list(queue) if queue else [],
        )

    def clear_session(self, session_id: str) -> None:
        """清空会话队列与暂停标记（会话删除/重置时调用，防止残留项后续被误发起）。"""
        self._queues.pop(session_id, None)
        self._paused.discard(session_id)
