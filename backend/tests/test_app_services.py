import importlib
import sys
import types


def test_agent_service_lazy_initialization_uses_websocket_broadcaster(monkeypatch):
    created = {}
    manager = object()

    class FakeWebSocketConversationBroadcaster:
        def __init__(self, injected_manager):
            self.manager = injected_manager

    class FakeAgentService:
        def __init__(self, *, conversation_broadcaster):
            created["conversation_broadcaster"] = conversation_broadcaster

    monkeypatch.setitem(
        sys.modules,
        "app.api.websocket_manager",
        types.SimpleNamespace(ws_manager=manager),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.conversation_broadcaster",
        types.SimpleNamespace(WebSocketConversationBroadcaster=FakeWebSocketConversationBroadcaster),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.services.agent_service",
        types.SimpleNamespace(AgentService=FakeAgentService),
    )

    app_services = importlib.import_module("app.app_services")
    monkeypatch.setattr(app_services, "_agent_service", None)
    monkeypatch.setattr(app_services, "_conversation_broadcaster", None)

    _ = app_services.agent_service

    broadcaster = created["conversation_broadcaster"]
    assert isinstance(broadcaster, FakeWebSocketConversationBroadcaster)
    assert broadcaster.manager is manager
