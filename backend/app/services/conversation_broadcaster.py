from typing import Protocol

from app.api.websocket_manager import ws_manager

# 属于是抽象类，定义了发送事件的接口
class ConversationBroadcaster(Protocol):
    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        """Publish a conversation event to interested clients."""


class WebSocketConversationBroadcaster:
    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        await ws_manager.send_event(session_id, event_type, data)


conversation_broadcaster = WebSocketConversationBroadcaster()
