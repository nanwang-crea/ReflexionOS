"""消息发送队列的 WebSocket 层集成测试：走真实路由分支 + 真实 WebSocket 广播器。

覆盖：
- conversation:sync 收尾时下发队列快照；
- 会话忙碌时 conversation:start_turn 自动入队（不再报"已有活跃轮次"错误）；
- queue_update / queue_remove / queue_send_now / queue_resume / queue_list 五个命令；
- 取消运行后队列自动暂停的广播。
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.llm_config import ProviderType, ResolvedLLMConfig
from app.models.project import Project
from app.models.session import Session
from app.services.agent_service import AgentService
from app.services.conversation_broadcaster import WebSocketConversationBroadcaster
from app.services.conversation_service import ConversationService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


def _drain_until_synced_with_queue(websocket):
    """读取消息直到 conversation:synced，并继续读一条紧随其后的 conversation:queue_state。"""
    messages = []
    while True:
        message = websocket.receive_json()
        messages.append(message)
        if message["type"] == "conversation:synced":
            break
    queue_state = websocket.receive_json()
    assert queue_state["type"] == "conversation:queue_state"
    return messages, queue_state["data"]


def _drain_until_queue_state(websocket):
    """读取消息直到下一条 conversation:queue_state（跳过途中的 conversation:event 等）。"""
    while True:
        message = websocket.receive_json()
        if message["type"] == "conversation:queue_state":
            return message["data"]
        if message["type"] == "conversation:error":
            raise AssertionError(f"意外收到错误消息: {message}")


@pytest.fixture
def client_with_idle_session(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "conversation-queue-ws.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(tmp_path)))
    session_repo.create(Session(id="session-1", project_id="project-1", title="需求讨论"))

    conversation_service = ConversationService(db=db)

    import app.api.websocket_manager as websocket_module

    websocket_module.ws_manager.active_connections.clear()
    agent_service = AgentService(
        project_repo=project_repo,
        session_repo=session_repo,
        conversation_service=conversation_service,
        conversation_broadcaster=WebSocketConversationBroadcaster(websocket_module.ws_manager),
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
    # schedule_turn 置空：发起轮次但不真正执行（Run 停在 CREATED，会话保持"忙碌"）
    monkeypatch.setattr(agent_service, "schedule_turn", lambda **kwargs: None)

    import app.api.routes.websocket as websocket_route_module

    monkeypatch.setattr(websocket_route_module, "conversation_service", conversation_service)
    monkeypatch.setattr(websocket_route_module, "agent_service", agent_service)

    with TestClient(app) as test_client:
        yield test_client, conversation_service, agent_service


def test_websocket_sync_delivers_queue_state_after_synced(client_with_idle_session):
    client, _, agent_service = client_with_idle_session
    agent_service.message_queues.enqueue("session-1", content="预置排队消息")

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json({"type": "conversation:sync", "data": {"after_seq": 0}})
        _, queue_state = _drain_until_synced_with_queue(websocket)

    assert queue_state["session_id"] == "session-1"
    assert queue_state["paused"] is False
    assert [item["content"] for item in queue_state["items"]] == ["预置排队消息"]


def test_websocket_start_turn_enqueues_when_session_busy(client_with_idle_session):
    client, conversation_service, _ = client_with_idle_session

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json({"type": "conversation:sync", "data": {"after_seq": 0}})
        _drain_until_synced_with_queue(websocket)

        # 第一条：会话空闲 → 直接发起新轮次（产生 conversation:event 种子事件）
        websocket.send_json({
            "type": "conversation:start_turn",
            "data": {"content": "第一轮", "provider_id": "provider-a", "model_id": "model-a"},
        })
        first_message = websocket.receive_json()
        assert first_message["type"] == "conversation:event"

        # 第二条：会话忙碌 → 自动入队并广播队列快照（不再报"已有活跃轮次"错误）
        websocket.send_json({
            "type": "conversation:start_turn",
            "data": {"content": "排队消息", "provider_id": "provider-a", "model_id": "model-a"},
        })
        queue_state = _drain_until_queue_state(websocket)

    assert queue_state["paused"] is False
    assert [item["content"] for item in queue_state["items"]] == ["排队消息"]
    assert len(conversation_service.get_snapshot("session-1").turns) == 1


def test_websocket_queue_commands_update_remove_send_now_and_resume(client_with_idle_session):
    client, conversation_service, agent_service = client_with_idle_session

    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json({"type": "conversation:sync", "data": {"after_seq": 0}})
        _drain_until_synced_with_queue(websocket)

        # 占住会话：start_turn 依次广播 turn.created / message.created / run.created 三个种子事件
        websocket.send_json({
            "type": "conversation:start_turn",
            "data": {"content": "第一轮", "provider_id": "provider-a", "model_id": "model-a"},
        })
        for _ in range(3):
            seed = websocket.receive_json()
            assert seed["type"] == "conversation:event"
        first = agent_service.message_queues.enqueue("session-1", content="排队消息A")
        second = agent_service.message_queues.enqueue("session-1", content="排队消息B")
        # 直接操作 manager 不产生广播，通过 queue_list 拉取当前快照对齐状态
        websocket.send_json({"type": "conversation:queue_list", "data": {}})
        state = _drain_until_queue_state(websocket)
        assert [item["id"] for item in state["items"]] == [first.id, second.id]

        # 编辑：原位更新内容
        websocket.send_json({
            "type": "conversation:queue_update",
            "data": {"queue_id": second.id, "content": "排队消息B（已编辑）"},
        })
        state = _drain_until_queue_state(websocket)
        assert state["items"][1]["content"] == "排队消息B（已编辑）"

        # 立即发送：会话忙碌 → 只调整顺序，不创建新轮次
        websocket.send_json({
            "type": "conversation:queue_send_now",
            "data": {"queue_id": second.id},
        })
        state = _drain_until_queue_state(websocket)
        assert [item["id"] for item in state["items"]] == [second.id, first.id]
        assert len(conversation_service.get_snapshot("session-1").turns) == 1

        # 删除：移除队首
        websocket.send_json({
            "type": "conversation:queue_remove",
            "data": {"queue_id": second.id},
        })
        state = _drain_until_queue_state(websocket)
        assert [item["id"] for item in state["items"]] == [first.id]

        # 未知 queue_id 的编辑 → conversation:error
        websocket.send_json({
            "type": "conversation:queue_update",
            "data": {"queue_id": "qmsg-missing", "content": "任意"},
        })
        error_message = websocket.receive_json()
        assert error_message["type"] == "conversation:error"

        # 取消当前 Run（队列非空 → 自动暂停并广播）
        active_run_id = conversation_service.get_snapshot("session-1").session.active_turn_id
        run_id = next(
            run.id
            for run in conversation_service.get_snapshot("session-1").runs
            if run.turn_id == active_run_id
        )
        websocket.send_json({
            "type": "conversation:cancel_run",
            "data": {"run_id": run_id},
        })
        state = _drain_until_queue_state(websocket)
        assert state["paused"] is True

        # 恢复：会话已空闲 → 自动出队发起新轮次，队列清空。
        # resume 先广播一次快照（仍含 A），出队发起完成后再次广播（已清空）——读到清空那条为止
        websocket.send_json({"type": "conversation:queue_resume", "data": {}})
        state = _drain_until_queue_state(websocket)
        while state["items"]:
            state = _drain_until_queue_state(websocket)
        assert state["paused"] is False

    snapshot = conversation_service.get_snapshot("session-1")
    assert len(snapshot.turns) == 2
