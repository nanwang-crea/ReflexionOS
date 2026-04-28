from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.project import Project
from app.models.session import Session
from app.services.agent_service import AgentService
from app.services.conversation_service import ConversationService
from app.services.session_service import SessionService
from app.storage.database import Database
from app.storage.repositories.message_search_document_repo import MessageSearchDocumentRepository
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "conversation-api.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_repo.create(Session(id="session-1", project_id="project-1", title="需求讨论"))

    session_service = SessionService(session_repo=session_repo, project_repo=project_repo)
    conversation_service = ConversationService(db=db)
    conversation_service.start_turn(
        session_id="session-1",
        content="请总结今天进展",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(Path("/tmp/reflexion")),
    )

    import app.api.routes.sessions as sessions_route_module

    monkeypatch.setattr(sessions_route_module, "session_service", session_service)
    monkeypatch.setattr(sessions_route_module, "conversation_service", conversation_service)

    with TestClient(app) as test_client:
        yield test_client


class _StubLLMResponse:
    def __init__(self, content: str):
        self.content = content


class _StubLLM:
    def __init__(self, *, content: str):
        self._content = content

    async def complete(self, _messages, tools=None):
        return _StubLLMResponse(self._content)


@pytest.fixture
def client_with_memory_pipeline(tmp_path, monkeypatch):
    """
    API-level fixture that exposes ConversationService so tests can assert on
    derived message search docs + continuation artifact persistence.
    """

    from types import SimpleNamespace

    db = Database(str(tmp_path / "conversation-api-memory-pipeline.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(tmp_path)))
    session_repo.create(Session(id="session-1", project_id="project-1", title="需求讨论"))

    session_service = SessionService(session_repo=session_repo, project_repo=project_repo)
    conversation_service = ConversationService(db=db)
    agent_service = AgentService(
        project_repo=project_repo,
        session_repo=session_repo,
        conversation_service=conversation_service,
    )
    monkeypatch.setattr(agent_service, "schedule_turn", lambda **kwargs: None)

    import app.api.routes.sessions as sessions_route_module

    monkeypatch.setattr(sessions_route_module, "session_service", session_service)
    monkeypatch.setattr(sessions_route_module, "conversation_service", conversation_service)

    with TestClient(app) as test_client:
        yield SimpleNamespace(
            client=test_client,
            db=db,
            tmp_path=tmp_path,
            project_repo=project_repo,
            session_repo=session_repo,
            conversation_service=conversation_service,
            agent_service=agent_service,
        )


def test_get_conversation_snapshot_returns_normalized_entities(client):
    response = client.get("/api/sessions/session-1/conversation")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"session", "turns", "runs", "messages"}
    assert "rounds" not in payload
    assert payload["session"]["id"] == "session-1"
    assert payload["session"]["last_event_seq"] == 3
    assert len(payload["turns"]) == 1
    assert len(payload["runs"]) == 1
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["message_type"] == "user_message"
    assert payload["messages"][0]["turn_message_index"] == 1


def test_get_conversation_snapshot_returns_404_for_missing_session(client):
    response = client.get("/api/sessions/missing-session/conversation")

    assert response.status_code == 404
    assert response.json() == {"detail": "会话不存在"}


@pytest.mark.asyncio
async def test_get_conversation_snapshot_includes_continuation_artifact_and_search_docs_exclude_it(
    client_with_memory_pipeline,
):
    """
    API verification:
    - snapshot surfaces messages (including derived system_notice continuation artifacts)
    - message_search_documents are derived for normal messages
    - continuation artifacts are excluded from recall/search indexing
    """

    from app.services.conversation_runtime_adapter import ConversationRuntimeAdapter

    services = client_with_memory_pipeline
    conversation_service = services.conversation_service
    agent_service = services.agent_service

    started = conversation_service.start_turn(
        session_id="session-1",
        content="请总结今天进展，并记住默认用中文回复",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(services.tmp_path),
    )

    runtime = ConversationRuntimeAdapter(
        conversation_service=conversation_service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )
    runtime.handle_event("run:start", {})
    runtime.handle_event("llm:content", {"content": "好的，我会默认使用中文回复，并在后续总结进展。"})
    runtime.handle_event("run:complete", {})

    stub_llm = _StubLLM(content="当前目标: 汇总进展并保持默认中文回复")
    await agent_service._generate_and_persist_continuation_artifact(  # noqa: SLF001 - explicit end-to-end verification
        llm=stub_llm,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        task="请总结今天进展，并记住默认用中文回复",
    )

    response = services.client.get("/api/sessions/session-1/conversation")
    assert response.status_code == 200
    payload = response.json()

    assert set(payload.keys()) == {"session", "turns", "runs", "messages"}
    assert any(msg["message_type"] == "assistant_message" for msg in payload["messages"])
    assert any(
        msg["message_type"] == "system_notice"
        and (msg.get("payload_json") or {}).get("kind") == "continuation_artifact"
        for msg in payload["messages"]
    )

    snapshot = conversation_service.get_snapshot("session-1")
    artifact_ids = {
        m.id for m in snapshot.messages if (m.payload_json or {}).get("kind") == "continuation_artifact"
    }
    assert artifact_ids

    # Derived search docs exist for normal messages.
    message_search_repo = MessageSearchDocumentRepository(services.db)
    assert message_search_repo.get(started.user_message.id) is not None
    assistant_ids = [
        m.id for m in snapshot.messages if m.message_type.value == "assistant_message"
    ]
    assert assistant_ids
    assert message_search_repo.get(assistant_ids[0]) is not None

    # ...but continuation artifacts are excluded from recall/search indexing.
    assert all(message_search_repo.get(msg_id) is None for msg_id in artifact_ids)
