from datetime import datetime, timedelta
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
        agent_service.llm_provider_service,
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


@pytest.fixture
def client_with_memory_pipeline(tmp_path, monkeypatch):
    """
    A slightly richer fixture than client_with_services:
    - wires AgentService + ConversationService into websocket routes
    - isolates curated memory base_dir to tmp_path
    - exposes services so tests can assert on pipeline artifacts (continuation + curated memory)
    """

    from types import SimpleNamespace

    db = Database(str(tmp_path / "conversation-websocket-memory-pipeline.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)

    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(tmp_path)))
    session_repo.create(Session(id="session-1", project_id="project-1", title="需求讨论"))

    # Make the project look like a real workspace for ContextAssembler (AGENTS.md is optional but stable to assert).
    (tmp_path / "AGENTS.md").write_text("# Project Rules\n\n- Always reply in Chinese.\n", encoding="utf-8")

    # Avoid writing curated memory into the real home directory during tests.
    from app.config.settings import config_manager

    monkeypatch.setattr(config_manager.settings.memory, "base_dir", str(tmp_path / "memories"))

    conversation_service = ConversationService(db=db)

    agent_service = AgentService(
        project_repo=project_repo,
        session_repo=session_repo,
        conversation_service=conversation_service,
    )
    monkeypatch.setattr(
        agent_service.llm_provider_service,
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
    # We don't want to run the full RapidExecutionLoop in websocket tests; we will drive artifacts explicitly.
    monkeypatch.setattr(agent_service, "schedule_turn", lambda **kwargs: None)

    import app.api.routes.websocket as websocket_route_module
    import app.api.websocket as websocket_module

    websocket_module.ws_manager.active_connections.clear()
    monkeypatch.setattr(websocket_route_module, "conversation_service", conversation_service)
    monkeypatch.setattr(websocket_route_module, "agent_service", agent_service)

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


def test_session_conversation_websocket_sync_includes_live_state_before_synced(client_with_services, monkeypatch):
    client, _ = client_with_services

    import app.api.routes.websocket as websocket_route_module

    monkeypatch.setattr(
        websocket_route_module.agent_service,
        "get_live_state",
        lambda session_id: {
            "session_id": session_id,
            "turn_id": "turn-live",
            "run_id": "run-live",
            "message_id": "msg-live",
            "message_type": "assistant_message",
            "content_text": "streaming...",
            "stream_state": "streaming",
        },
    )

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json({"type": "conversation.sync", "data": {"after_seq": 0}})
        messages = _drain_until_synced(websocket)

    assert [message["type"] for message in messages[-2:]] == [
        "conversation.live_state",
        "conversation.synced",
    ]
    assert messages[-2]["data"]["content_text"] == "streaming..."


def test_session_conversation_websocket_requests_resync_for_stale_after_seq(client_with_services):
    client, conversation_service = client_with_services

    conversation_service.cleanup_events(
        now=datetime.now() + timedelta(days=8),
        completed_retention=timedelta(minutes=30),
        failed_retention=timedelta(days=7),
    )
    conversation_service.start_turn(
        session_id="session-1",
        content="新的活动轮次",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=str(Path("/tmp/reflexion")),
    )

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json({"type": "conversation.sync", "data": {"after_seq": 0}})
        message = websocket.receive_json()

    assert message["type"] == "conversation.resync_required"
    assert message["data"]["reason"] == "stale_after_seq"


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


@pytest.mark.asyncio
async def test_resumed_session_rehydrates_recent_messages_and_curated_memory(client_with_memory_pipeline):
    """
    End-to-end verification for Phase 1 memory pipeline:
    - messages are the primary reading surface (snapshot + context assembly)
    - curated memory persists under settings.memory.base_dir/projects/<project_id>/
    - continuation artifacts are persisted as derived system_notice messages and become supplemental context
    - recall/search docs index normal messages but exclude continuation artifacts
    """

    from app.memory.context_assembly import ContextAssembler
    from app.memory.continuation import build_continuation_artifact
    from app.memory.curated_store import CuratedMemoryStore, CuratedEntry
    from app.memory.recall_service import RecallService
    from app.services.conversation_service import ConversationService
    from app.services.conversation_runtime_adapter import ConversationRuntimeAdapter
    from app.models.conversation import ConversationEvent, EventType
    from app.tools.memory_tool import MemoryTool

    services = client_with_memory_pipeline
    client = services.client
    conversation_service = services.conversation_service

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json(
            {
                "type": "conversation.start_turn",
                "data": {
                    "content": "请记住默认使用中文回复",
                    "provider_id": "provider-a",
                    "model_id": "model-a",
                },
            }
        )

        seed_events = [websocket.receive_json() for _ in range(3)]
        assert [message["type"] for message in seed_events] == ["conversation.event"] * 3
        assert [message["data"]["event_type"] for message in seed_events] == [
            "turn.created",
            "message.created",
            "run.created",
        ]
        turn_id = seed_events[0]["data"]["turn_id"]
        run_id = seed_events[2]["data"]["run_id"]

        # Simulate a completed run producing assistant output through the runtime adapter,
        # so derived message_search_documents are also exercised.
        runtime = ConversationRuntimeAdapter(
            conversation_service=conversation_service,
            session_id="session-1",
            turn_id=turn_id,
            run_id=run_id,
        )
        runtime.handle_event("run:start", {})
        runtime.handle_event("llm:content", {"content": "好的，我会默认使用中文回复。"})
        runtime.handle_event("run:complete", {})

        # Add curated memory entry via tool (writes USER.md / curated_user.json).
        memory_tool = MemoryTool(store=CuratedMemoryStore())
        entry = CuratedEntry(
            target="user",
            type="preference",
            scope="project",
            source="user_explicit",
            confidence="high",
            status="active",
            source_refs=["msg-user-seed"],
            summary="默认使用中文回复。",
        )
        result = await memory_tool.execute(
            {
                "action": "add",
                "project_id": "project-1",
                "entry": entry.model_dump(mode="json"),
            }
        )
        assert result.success is True

        # Persist a continuation artifact as a derived system_notice message through the normal event path.
        next_index = conversation_service.message_repo.next_turn_message_index(turn_id)
        artifact = build_continuation_artifact(
            session_id="session-1",
            turn_id=turn_id,
            content_text="\n".join(
                [
                    "当前目标: 保持默认中文回复",
                    "下一步建议: 继续完成 API 验证用例",
                ]
            ),
            turn_message_index=next_index,
        )
        conversation_service.append_events(
            "session-1",
            [
                ConversationEvent(
                    id="evt-cont-created",
                    session_id="session-1",
                    turn_id=turn_id,
                    run_id=run_id,
                    message_id=artifact.id,
                    event_type=EventType.MESSAGE_CREATED,
                    payload_json={
                        "message_id": artifact.id,
                        "turn_id": artifact.turn_id,
                        "run_id": artifact.run_id,
                        "role": artifact.role,
                        "message_type": artifact.message_type.value,
                        "turn_message_index": artifact.turn_message_index,
                        "display_mode": artifact.display_mode,
                        "content_text": artifact.content_text,
                        "payload_json": artifact.payload_json,
                    },
                ),
                ConversationEvent(
                    id="evt-cont-completed",
                    session_id="session-1",
                    turn_id=turn_id,
                    run_id=run_id,
                    message_id=artifact.id,
                    event_type=EventType.MESSAGE_COMPLETED,
                    payload_json={
                        "completed_at": None,
                    },
                ),
            ],
        )

        # Resume flow: a fresh sync should surface all recent conversation state (including derived notice).
        websocket.send_json({"type": "conversation.sync", "data": {"after_seq": 0}})
        replay = _drain_until_synced(websocket)
        assert any(msg["type"] == "conversation.event" for msg in replay)

    # "Resumed session" rehydration: fresh service objects should be able to reconstruct state from storage.
    fresh_conversation_service = ConversationService(db=services.db)
    snapshot = fresh_conversation_service.get_snapshot("session-1")
    assert any((m.content_text or "").strip() for m in snapshot.messages)
    assert any((m.payload_json or {}).get("kind") == "continuation_artifact" for m in snapshot.messages)

    curated_dir = services.tmp_path / "memories" / "projects" / "project-1"
    assert (curated_dir / "USER.md").exists()
    assert "默认使用中文回复。" in (curated_dir / "USER.md").read_text(encoding="utf-8")

    # Context assembly should pick up:
    # - static blocks: AGENTS.md + curated USER
    # - recent messages: user + assistant messages
    # - supplemental: latest continuation artifact
    assembler = ContextAssembler(
        conversation_service=ConversationService(db=services.db),
        curated_store=CuratedMemoryStore(base_dir=services.tmp_path / "memories"),
    )
    assembly = assembler.build_for_session(
        session_id="session-1",
        project_id="project-1",
        project_path=str(services.tmp_path),
    )
    assert any("Always reply in Chinese" in section for section in assembly.system_sections)
    assert any("默认使用中文回复" in section for section in assembly.system_sections)
    assert assembly.recent_messages
    assert assembly.supplemental_block is not None
    assert "当前目标" in assembly.supplemental_block

    # Recall reads from normalized derived search docs, and continuation artifacts stay excluded.
    recall = RecallService(db=services.db)
    results = recall.search(project_id="project-1", query="中文 回复", limit=3)
    assert results
    artifact_message_ids = {
        m.id
        for m in snapshot.messages
        if (m.payload_json or {}).get("kind") == "continuation_artifact"
    }
    assert not any(result.message_id in artifact_message_ids for result in results)
