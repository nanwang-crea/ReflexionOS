"""消息发送队列（参考 reflexion-os-studio 对齐项）的测试。

覆盖三层：
1. SessionMessageQueueManager 纯内存单元行为（入队/出队/编辑/删除/插队/暂停/上限/清理）；
2. AgentService 集成：忙碌入队、Run 终态自动出队、取消暂停、立即发送、出队失败保留并暂停、
   会话清理连带清队；
3. 队列快照广播负载的形状。
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.models.llm_config import LLMSettings
from app.models.project import Project
from app.models.session import Session
from app.services import agent_service as agent_service_module
from app.services.conversation_runtime_adapter import ConversationRuntimeAdapter
from app.services.conversation_service import ConversationService
from app.services.llm_provider_service import LLMProviderService
from app.services.message_queue_service import (
    MAX_QUEUE_SIZE_PER_SESSION,
    QueuedMessage,
    SessionMessageQueueManager,
)
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


# ---- 测试脚手架（与 test_agent_service.py 同构，因测试目录非包而本地复制） ----


class DummyConfigManager:
    def __init__(self, settings: LLMSettings | None = None):
        self.settings = SimpleNamespace(llm=settings or LLMSettings())


def build_provider(
    provider_id: str,
    name: str,
    model_ids: list[str],
):
    from app.models.llm_config import ProviderModelConfig, ProviderType

    models = [
        ProviderModelConfig(
            id=model_id,
            display_name=model_id.upper(),
            model_name=model_id,
            enabled=True,
        )
        for model_id in model_ids
    ]
    from app.models.llm_config import ProviderInstanceConfig

    return ProviderInstanceConfig(
        id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key="test-key",
        base_url="https://example.com/v1",
        models=models,
        default_model_id=models[0].id,
        enabled=True,
    )


def build_service_with_db(
    monkeypatch,
    tmp_path,
    *,
    project: Project | None = None,
    session: Session | None = None,
    settings: LLMSettings | None = None,
):
    db = Database(str(tmp_path / "agent-service.db"))
    dummy_config = DummyConfigManager(settings)

    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    if project is not None:
        project_repo.save(project)
    if session is not None:
        session_repo.create(session)

    conversation_service = ConversationService(db=db)
    provider_service = LLMProviderService(config_manager=dummy_config)
    service = agent_service_module.AgentService(
        project_repo=project_repo,
        session_repo=session_repo,
        conversation_service=conversation_service,
        llm_provider_service=provider_service,
    )
    return service, conversation_service, dummy_config


# ---------------------------------------------------------------------------
# 1) SessionMessageQueueManager 纯内存单元行为
# ---------------------------------------------------------------------------


def test_enqueue_peek_pop_preserves_fifo_order():
    manager = SessionMessageQueueManager()
    first = manager.enqueue("s1", content="第一条")
    second = manager.enqueue("s1", content="第二条")

    assert manager.peek("s1") is first
    assert manager.pop("s1") is first
    assert manager.pop("s1") is second
    assert manager.pop("s1") is None
    assert manager.is_empty("s1")


def test_update_rewrites_content_in_place():
    manager = SessionMessageQueueManager()
    item = manager.enqueue("s1", content="原始内容")

    updated = manager.update("s1", item.id, content="修改后的内容")

    assert updated.content == "修改后的内容"
    assert manager.peek("s1").content == "修改后的内容"


def test_update_unknown_id_raises():
    manager = SessionMessageQueueManager()
    manager.enqueue("s1", content="内容")
    with pytest.raises(ValueError):
        manager.update("s1", "qmsg-missing", content="任意")


def test_remove_deletes_single_item():
    manager = SessionMessageQueueManager()
    first = manager.enqueue("s1", content="第一条")
    manager.enqueue("s1", content="第二条")

    assert manager.remove("s1", first.id) is True
    assert manager.peek("s1").content == "第二条"
    assert manager.remove("s1", first.id) is False


def test_move_to_front_reorders_queue():
    manager = SessionMessageQueueManager()
    manager.enqueue("s1", content="第一条")
    second = manager.enqueue("s1", content="第二条")

    manager.move_to_front("s1", second.id)

    assert manager.peek("s1") is second
    assert [item.content for item in manager.get_snapshot("s1").items] == ["第二条", "第一条"]


def test_enqueue_rejects_when_queue_full():
    manager = SessionMessageQueueManager(max_size_per_session=2)
    manager.enqueue("s1", content="第一条")
    manager.enqueue("s1", content="第二条")
    with pytest.raises(ValueError, match="消息队列已满"):
        manager.enqueue("s1", content="第三条")
    # 队列满不影响其他会话
    manager.enqueue("s2", content="另一会话")


def test_pause_resume_and_snapshot():
    manager = SessionMessageQueueManager()
    manager.enqueue("s1", content="第一条")

    assert manager.is_paused("s1") is False
    manager.pause("s1")
    assert manager.is_paused("s1") is True
    assert manager.resume("s1") is True
    assert manager.resume("s1") is False
    assert manager.is_paused("s1") is False

    snapshot = manager.get_snapshot("s1")
    assert snapshot.session_id == "s1"
    assert snapshot.paused is False
    assert len(snapshot.items) == 1


def test_clear_session_drops_queue_and_pause_flag():
    manager = SessionMessageQueueManager()
    manager.enqueue("s1", content="第一条")
    manager.pause("s1")

    manager.clear_session("s1")

    assert manager.is_empty("s1")
    assert manager.is_paused("s1") is False


def test_queued_message_to_dict_shape():
    item = QueuedMessage(content="内容", provider_id="p1", model_id="m1", attachment_ids=["a1"])
    data = item.to_dict()
    assert data["id"] == item.id
    assert data["content"] == "内容"
    assert data["attachment_ids"] == ["a1"]
    assert data["provider_id"] == "p1"
    assert data["model_id"] == "m1"
    assert "created_at" in data


# ---------------------------------------------------------------------------
# 2) AgentService 集成：入队 / 自动出队 / 取消暂停 / 立即发送 / 失败保留
# ---------------------------------------------------------------------------


def _build_settings() -> LLMSettings:
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    return LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )


class RecordingBroadcaster:
    def __init__(self):
        self.sent: list[tuple[str, str, dict]] = []

    async def send_event(self, session_id, event_type, data):
        self.sent.append((session_id, event_type, data))

    def queue_states(self):
        return [
            data for _, event_type, data in self.sent if event_type == "conversation:queue_state"
        ]


def _make_service(monkeypatch, tmp_path):
    project = Project(id="project-1", name="ReflexionOS", path=str(tmp_path))
    session = Session(id="session-1", project_id="project-1", title="需求讨论")
    service, conversation_service, _ = build_service_with_db(
        monkeypatch,
        tmp_path,
        project=project,
        session=session,
        settings=_build_settings(),
    )
    broadcaster = RecordingBroadcaster()
    service.conversation_broadcaster = broadcaster
    return service, conversation_service, broadcaster


def _fake_run_turn_completing(conversation_service, on_settled=None):
    """构造一个"被调用即完整结束"的 fake _run_turn：落库 run:complete 终态（清空活跃轮次）。

    on_settled：模拟真实 _run_turn finally 中的队列出队钩子（如 service._pump_message_queue）。
    """

    async def fake_run_turn(**kwargs):
        adapter = ConversationRuntimeAdapter(
            conversation_service=conversation_service,
            session_id=kwargs["session_id"],
            turn_id=kwargs["turn_id"],
            run_id=kwargs["run_id"],
        )
        adapter.handle_event("run:complete", {})
        if on_settled is not None:
            await on_settled(kwargs["session_id"])

    return fake_run_turn


def _fake_run_turn_holding(
    *, complete_on_release: bool = False, conversation_service=None, on_settled=None
):
    """构造一个"挂起直到放行"的 fake _run_turn，用于模拟会话忙碌。

    complete_on_release=True 时，放行后会补落 run:complete 终态（模拟真实执行循环正常结束，
    从而触发队列出队）；False 时直接返回（Run 仍停留在非终态）。
    on_settled：终态后模拟真实 _run_turn finally 的出队钩子（如 service._pump_message_queue）。
    started/finish 事件在同一测试内的多次运行间共享：已放行的事件对后续运行立即生效，
    因此"完成链"会在队列清空后自然收敛。
    """
    started_event = asyncio.Event()
    finish_event = asyncio.Event()
    run_ids: list[str] = []

    async def fake_run_turn(**kwargs):
        run_ids.append(kwargs["run_id"])
        started_event.set()
        await finish_event.wait()
        if complete_on_release:
            adapter = ConversationRuntimeAdapter(
                conversation_service=conversation_service,
                session_id=kwargs["session_id"],
                turn_id=kwargs["turn_id"],
                run_id=kwargs["run_id"],
            )
            adapter.handle_event("run:complete", {})
            if on_settled is not None:
                await on_settled(kwargs["session_id"])

    return fake_run_turn, started_event, finish_event, run_ids


async def _drain_runs(service, max_rounds: int = 6) -> None:
    """等待所有已调度的运行任务结束（完成一次运行可能经出队触发点产生下一轮任务）。"""
    for _ in range(max_rounds):
        tasks = list(service.running_tasks.values())
        if not tasks:
            await asyncio.sleep(0)
            return
        await asyncio.gather(*(asyncio.wait_for(task, timeout=2) for task in tasks))


@pytest.mark.asyncio
async def test_submit_message_starts_turn_when_session_idle(monkeypatch, tmp_path):
    service, conversation_service, broadcaster = _make_service(monkeypatch, tmp_path)
    monkeypatch.setattr(
        service, "_run_turn", _fake_run_turn_completing(conversation_service)
    )

    result = await service.submit_message(
        project_id="project-1",
        session_id="session-1",
        content="请检查仓库",
        provider_id="provider-a",
        model_id="model-a",
    )

    assert hasattr(result, "turn")  # StartTurnResult：直接发起而非入队
    assert service.message_queues.is_empty("session-1")
    assert broadcaster.queue_states() == []
    await _drain_runs(service)


@pytest.mark.asyncio
async def test_submit_message_enqueues_when_run_active(monkeypatch, tmp_path):
    service, conversation_service, broadcaster = _make_service(monkeypatch, tmp_path)
    fake_run_turn, started_event, finish_event, _ = _fake_run_turn_holding()
    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="第一轮",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(started_event.wait(), timeout=0.5)

    queued = await service.submit_message(
        project_id="project-1",
        session_id="session-1",
        content="排队消息",
        provider_id="provider-a",
        model_id="model-a",
    )

    assert isinstance(queued, QueuedMessage)
    assert queued.content == "排队消息"
    states = broadcaster.queue_states()
    assert states and states[-1]["session_id"] == "session-1"
    assert states[-1]["paused"] is False
    assert [item["content"] for item in states[-1]["items"]] == ["排队消息"]

    # 会话仍只有一个活跃轮次：排队消息不会立即创建第二轮
    snapshot = conversation_service.get_snapshot("session-1")
    assert snapshot.session.active_turn_id == started.turn.id
    assert len(snapshot.turns) == 1

    finish_event.set()
    await _drain_runs(service)


@pytest.mark.asyncio
async def test_queue_auto_pumps_after_run_completes(monkeypatch, tmp_path):
    service, conversation_service, _ = _make_service(monkeypatch, tmp_path)
    fake_run_turn, started_event, finish_event, run_ids = _fake_run_turn_holding(
        complete_on_release=True,
        conversation_service=conversation_service,
        on_settled=service._pump_message_queue,
    )
    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="第一轮",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(started_event.wait(), timeout=0.5)

    await service.submit_message(
        project_id="project-1", session_id="session-1", content="排队消息A"
    )

    # 第一轮结束 → _run_turn finally 中的出队触发点自动发起"排队消息A"
    finish_event.set()
    await _drain_runs(service)

    snapshot = conversation_service.get_snapshot("session-1")
    assert len(snapshot.turns) == 2
    assert len(run_ids) == 2
    assert service.message_queues.is_empty("session-1")
    assert service.running_tasks == {}


@pytest.mark.asyncio
async def test_cancel_run_pauses_nonempty_queue_and_resume_pumps(monkeypatch, tmp_path):
    service, conversation_service, broadcaster = _make_service(monkeypatch, tmp_path)
    fake_run_turn, started_event, finish_event, _ = _fake_run_turn_holding()
    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="第一轮",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(started_event.wait(), timeout=0.5)

    await service.submit_message(
        project_id="project-1", session_id="session-1", content="排队消息A"
    )

    # 用户主动取消且队列非空 → 队列自动暂停，排队消息不被发起
    await service.cancel_run(started.run.id)

    assert conversation_service.get_run(started.run.id).status.value == "cancelled"
    state = service.get_message_queue_state("session-1")
    assert state["paused"] is True
    assert [item["content"] for item in state["items"]] == ["排队消息A"]
    assert broadcaster.queue_states()[-1]["paused"] is True

    # 恢复队列：会话已空闲，应自动出队发起"排队消息A"（fake 直接落终态）
    monkeypatch.setattr(
        service, "_run_turn", _fake_run_turn_completing(conversation_service)
    )
    await service.resume_message_queue("session-1")
    await _drain_runs(service)

    state = service.get_message_queue_state("session-1")
    assert state["paused"] is False
    assert state["items"] == []
    assert len(conversation_service.get_snapshot("session-1").turns) == 2


@pytest.mark.asyncio
async def test_cancel_run_keeps_queue_unpaused_when_empty(monkeypatch, tmp_path):
    service, conversation_service, _ = _make_service(monkeypatch, tmp_path)
    fake_run_turn, started_event, finish_event, _ = _fake_run_turn_holding()
    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="第一轮",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(started_event.wait(), timeout=0.5)

    await service.cancel_run(started.run.id)

    state = service.get_message_queue_state("session-1")
    assert state["paused"] is False
    assert state["items"] == []


@pytest.mark.asyncio
async def test_send_now_moves_item_to_front_and_pumps_when_idle(monkeypatch, tmp_path):
    service, conversation_service, _ = _make_service(monkeypatch, tmp_path)
    fake_run_turn, started_event, finish_event, _ = _fake_run_turn_holding()
    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="第一轮",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(started_event.wait(), timeout=0.5)

    await service.submit_message(
        project_id="project-1", session_id="session-1", content="排队消息A"
    )
    second = await service.submit_message(
        project_id="project-1", session_id="session-1", content="排队消息B"
    )

    # 会话忙碌：立即发送只调整顺序，不打断当前 Run
    await service.send_queued_message_now("session-1", second.id)
    assert [item.content for item in service.message_queues.get_snapshot("session-1").items] == [
        "排队消息B",
        "排队消息A",
    ]
    assert len(conversation_service.get_snapshot("session-1").turns) == 1

    # 释放第一轮（不落终态，Run 保持非终态），用户取消 → 队列非空自动暂停
    finish_event.set()
    await _drain_runs(service)
    await service.cancel_run(started.run.id)
    assert service.message_queues.is_paused("session-1") is True

    # "立即发送"应解除暂停并出队发起；随后每轮结束继续按序消费剩余排队消息
    monkeypatch.setattr(
        service,
        "_run_turn",
        _fake_run_turn_completing(conversation_service, on_settled=service._pump_message_queue),
    )
    await service.send_queued_message_now("session-1", second.id)
    await _drain_runs(service)

    snapshot = conversation_service.get_snapshot("session-1")
    assert len(snapshot.turns) == 3
    assert service.message_queues.is_empty("session-1")
    assert service.message_queues.is_paused("session-1") is False


@pytest.mark.asyncio
async def test_pump_failure_retains_item_and_pauses_queue(monkeypatch, tmp_path):
    service, conversation_service, broadcaster = _make_service(monkeypatch, tmp_path)
    # 会话保持空闲（不创建任何轮次），把消息直接放入队列，再让 start_turn 失败
    # （模拟供应商配置失效等入队时无法发现的错误）
    item = service.message_queues.enqueue("session-1", content="会失败的排队消息")

    async def failing_start_turn(**kwargs):
        raise ValueError("供应商不存在或已禁用")

    monkeypatch.setattr(service, "start_turn", failing_start_turn)
    await service._pump_message_queue("session-1")

    state = service.get_message_queue_state("session-1")
    assert state["paused"] is True
    assert [entry["id"] for entry in state["items"]] == [item.id]
    # 失败的发起没有产生任何新轮次，消息也没有丢失
    assert conversation_service.get_snapshot("session-1").turns == []
    assert broadcaster.queue_states()[-1]["paused"] is True


@pytest.mark.asyncio
async def test_pump_clears_queue_when_session_missing(monkeypatch, tmp_path):
    service, _, _ = _make_service(monkeypatch, tmp_path)
    service.message_queues.enqueue("session-gone", content="孤儿消息")

    await service._pump_message_queue("session-gone")

    assert service.message_queues.is_empty("session-gone")


@pytest.mark.asyncio
async def test_update_and_remove_queued_message_broadcast_state(monkeypatch, tmp_path):
    service, _, broadcaster = _make_service(monkeypatch, tmp_path)
    item = service.message_queues.enqueue("session-1", content="原始内容")

    await service.update_queued_message("session-1", item.id, content="编辑后")
    state = service.get_message_queue_state("session-1")
    assert state["items"][0]["content"] == "编辑后"

    removed = await service.remove_queued_message("session-1", item.id)
    assert removed is True
    assert service.message_queues.is_empty("session-1")
    assert broadcaster.queue_states()[-1]["items"] == []

    assert await service.remove_queued_message("session-1", "qmsg-missing") is False


@pytest.mark.asyncio
async def test_submit_message_rejects_queue_overflow(monkeypatch, tmp_path):
    service, _, _ = _make_service(monkeypatch, tmp_path)
    fake_run_turn, started_event, finish_event, _ = _fake_run_turn_holding()
    monkeypatch.setattr(service, "_run_turn", fake_run_turn)

    started = await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="第一轮",
        provider_id="provider-a",
        model_id="model-a",
    )
    await asyncio.wait_for(started_event.wait(), timeout=0.5)

    for index in range(MAX_QUEUE_SIZE_PER_SESSION):
        await service.submit_message(
            project_id="project-1", session_id="session-1", content=f"消息{index}"
        )

    with pytest.raises(ValueError, match="消息队列已满"):
        await service.submit_message(
            project_id="project-1", session_id="session-1", content="超限消息"
        )

    finish_event.set()
    await _drain_runs(service)


@pytest.mark.asyncio
async def test_session_cleanup_clears_message_queue(monkeypatch, tmp_path):
    service, _, _ = _make_service(monkeypatch, tmp_path)
    service.message_queues.enqueue("session-1", content="排队消息")
    service.message_queues.pause("session-1")

    service.cleanup_session_security_state("session-1")

    assert service.message_queues.is_empty("session-1")
    assert service.message_queues.is_paused("session-1") is False


@pytest.mark.asyncio
async def test_submit_message_rejects_cross_project_session(monkeypatch, tmp_path):
    service, _, _ = _make_service(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="会话不属于当前项目"):
        await service.submit_message(
            project_id="project-other",
            session_id="session-1",
            content="任意内容",
        )
