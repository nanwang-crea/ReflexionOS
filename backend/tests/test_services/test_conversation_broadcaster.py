from app.services.conversation_broadcaster import WebSocketConversationBroadcaster


class RecordingManager:
    def __init__(self):
        self.sent_events = []

    async def send_event(self, session_id: str, event_type: str, data: dict) -> None:
        self.sent_events.append((session_id, event_type, data))


async def test_websocket_conversation_broadcaster_delegates_to_injected_manager():
    manager = RecordingManager()
    broadcaster = WebSocketConversationBroadcaster(manager)

    await broadcaster.send_event("session-1", "conversation.event", {"seq": 1})

    assert manager.sent_events == [
        ("session-1", "conversation.event", {"seq": 1}),
    ]
