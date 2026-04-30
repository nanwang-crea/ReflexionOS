from typing import Protocol


class ConversationBroadcaster(Protocol):
    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        """Publish a conversation event to interested clients."""


class WebSocketManager(Protocol):
    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        """Send a websocket event to one session."""


class NoopConversationBroadcaster:
    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        return None


class WebSocketConversationBroadcaster:
    def __init__(self, manager: WebSocketManager):
        self._manager = manager

    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        await self._manager.send_event(session_id, event_type, data)
