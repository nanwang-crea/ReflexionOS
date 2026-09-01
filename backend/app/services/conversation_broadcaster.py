"""会话事件广播接口：定义向前端推送对话事件的抽象协议，屏蔽底层 WebSocket 连接管理器的具体实现，
便于测试时替换为空实现（NoopConversationBroadcaster）。"""

from typing import Protocol


class ConversationBroadcaster(Protocol):
    """会话事件广播协议：实现方需提供 send_event 方法，将事件推送给关注该会话的客户端。"""

    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        """Publish a conversation event to interested clients."""


class NoopConversationBroadcaster:
    """空实现广播器：不做任何推送，用于测试或未启用实时推送的场景。"""

    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        """空操作：接口调用直接返回，不产生任何副作用。
        输入：session_id（会话 ID）、event_type（事件类型）、data（事件负载）
        输出：无
        """
        return None


class WebSocketConversationBroadcaster:
    """基于 WebSocket 连接管理器的广播器：将事件转发给底层 manager 完成实际推送。"""

    def __init__(self, manager: ConversationBroadcaster):
        """初始化广播器。
        输入：manager（实际负责连接管理和推送的对象，如 WebSocket ConnectionManager）
        """
        self._manager = manager

    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        """将事件转发给底层连接管理器进行推送。
        输入：session_id（目标会话 ID）、event_type（事件类型）、data（事件负载，需可 JSON 序列化）
        输出：无
        """
        await self._manager.send_event(session_id, event_type, data)
