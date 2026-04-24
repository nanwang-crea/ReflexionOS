from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.llm_config import ProviderType, ResolvedLLMConfig
from app.models.project import Project
from app.models.session import Session
from app.services.agent_service import AgentService
from app.services.conversation_service import ConversationService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


def _drain_until_synced(websocket):
    messages = []
    while True:
        message = websocket.receive_json()
        messages.append(message)
        if message["type"] == "conversation.synced":
            return messages


@pytest.fixture
def client_with_services(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "conversation-websocket.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(tmp_path)))
    session_repo.create(Session(id="session-1", project_id="project-1", title="需求讨论"))

    conversation_service = ConversationService(db=db)
    seeded = conversation_service.start_turn(
        session_id="session-1",
        content="先做一轮初始化",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(tmp_path),
    )
    conversation_service.cancel_run(seeded.run.id)

    agent_service = AgentService(
        project_repo=project_repo,
        session_repo=session_repo,
        conversation_service=conversation_service,
    )
    monkeypatch.setattr(
        agent_service,
        "resolve_llm_config",
        lambda provider_id=None, model_id=None: ResolvedLLMConfig(
            provider_id=provider_id or "provider-a",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            model_id=model_id or "model-a",
            model="stub-model",
            temperature=0.7,
            max_tokens=256,
        ),
    )
    monkeypatch.setattr(agent_service, "schedule_turn", lambda **kwargs: None)

    import app.api.routes.websocket as websocket_route_module
    import app.api.websocket as websocket_module

    websocket_module.ws_manager.active_connections.clear()
    monkeypatch.setattr(websocket_route_module, "conversation_service", conversation_service)
    monkeypatch.setattr(websocket_route_module, "agent_service", agent_service)

    with TestClient(app) as test_client:
        yield test_client, conversation_service


def test_session_conversation_websocket_supports_sync_and_start_turn(client_with_services):
    client, conversation_service = client_with_services

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json({"type": "conversation.sync", "data": {"after_seq": 0}})
        synced_messages = _drain_until_synced(websocket)
        event_messages = [message for message in synced_messages if message["type"] == "conversation.event"]
        assert event_messages
        assert synced_messages[-1]["type"] == "conversation.synced"
        assert synced_messages[-1]["data"]["session_id"] == "session-1"

        websocket.send_json(
            {
                "type": "conversation.start_turn",
                "data": {
                    "content": "inspect repo",
                    "provider_id": "provider-a",
                    "model_id": "model-a",
                },
            }
        )

        seed_messages = [websocket.receive_json() for _ in range(3)]
        assert [message["type"] for message in seed_messages] == [
            "conversation.event",
            "conversation.event",
            "conversation.event",
        ]

        seed_event_types = [message["data"]["event_type"] for message in seed_messages]
        assert seed_event_types == ["turn.created", "message.created", "run.created"]

        seed_event_seqs = [message["data"]["seq"] for message in seed_messages]
        assert seed_event_seqs == sorted(seed_event_seqs)
        assert len(set(seed_event_seqs)) == 3

        websocket.send_json(
            {"type": "conversation.sync", "data": {"after_seq": seed_event_seqs[-1]}}
        )
        after_start_sync_messages = _drain_until_synced(websocket)
        replayed_events = [
            message
            for message in after_start_sync_messages
            if message["type"] == "conversation.event"
        ]

    assert replayed_events == []
    snapshot = conversation_service.get_snapshot("session-1")
    assert snapshot.session.last_event_seq == seed_event_seqs[-1]


def test_session_conversation_websocket_supports_live_cancel_run_update(client_with_services):
    client, conversation_service = client_with_services
    started = conversation_service.start_turn(
        session_id="session-1",
        content="待取消的任务",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(Path("/tmp/reflexion")),
    )

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json(
            {"type": "conversation.cancel_run", "data": {"run_id": started.run.id}}
        )
        cancel_messages = [websocket.receive_json(), websocket.receive_json()]

    assert [message["type"] for message in cancel_messages] == [
        "conversation.event",
        "conversation.event",
    ]
    assert [message["data"]["event_type"] for message in cancel_messages] == [
        "run.cancelled",
        "system.notice_emitted",
    ]
    cancelled_run = conversation_service.run_repo.get(started.run.id)
    assert cancelled_run is not None
    assert cancelled_run.status.value == "cancelled"
