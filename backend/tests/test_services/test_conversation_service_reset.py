import pytest

from app.errors import NotFoundValueError
from app.models.conversation import Run, RunStatus, Turn, TurnStatus
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.storage.database import Database


def _make_service(tmp_path, name: str) -> ConversationService:
    db = Database(str(tmp_path / f"{name}.db"))
    return ConversationService(db=db)


def _seed_turn_with_data(service: ConversationService, session_id: str, n: int) -> None:
    """用 start_turn 造真实的 turn/run/message/event，再补一条 search 文档。

    start_turn 要求上一轮已结束（active_turn_id 为空），因此每轮造完后把
    session.active_turn_id 清掉，模拟该轮完成，使下一轮可以开始。
    """
    for i in range(n):
        started = service.start_turn(
            session_id=session_id,
            content=f"task {i}",
            provider_id="provider-a",
            model_id="model-a",
            workspace_ref=None,
        )
        service.message_search_repo.upsert(
            message_id=started.user_message.id,
            session_id=session_id,
            turn_id=started.turn.id,
            run_id=started.run.id,
            role="user",
            message_type=started.user_message.message_type.value,
            turn_index=started.turn.turn_index,
            turn_message_index=started.user_message.turn_message_index,
            search_text=f"task {i}",
        )
        s = service.session_repo.get(session_id)
        service.session_repo.update(s.model_copy(update={"active_turn_id": None}))


def test_reset_clears_all_and_resets_counters(tmp_path):
    service = _make_service(tmp_path, "reset-clears")
    service.session_repo.create(Session(id="s1", project_id="p1", title="会话"))
    _seed_turn_with_data(service, "s1", n=3)

    # 前置：确有数据
    assert service.turn_repo.list_by_session("s1")
    assert service.run_repo.list_by_session("s1")
    assert service.session_repo.get("s1").last_event_seq > 0

    result = service.reset_session("s1")

    assert service.turn_repo.list_by_session("s1") == []
    assert service.run_repo.list_by_session("s1") == []
    snapshot = service.get_snapshot("s1")
    assert snapshot.turns == []
    assert snapshot.messages == []
    assert snapshot.runs == []
    assert result.active_turn_id is None
    assert result.last_event_seq == 0
    assert service.session_repo.get("s1").active_turn_id is None
    assert service.session_repo.get("s1").last_event_seq == 0


def test_reset_empty_session_is_idempotent(tmp_path):
    service = _make_service(tmp_path, "reset-empty")
    service.session_repo.create(Session(id="s1", project_id="p1", title="空会话"))

    result = service.reset_session("s1")

    assert result.active_turn_id is None
    assert result.last_event_seq == 0
    assert service.turn_repo.list_by_session("s1") == []
    # 再次重置仍无害
    again = service.reset_session("s1")
    assert again.last_event_seq == 0


def test_reset_does_not_touch_other_sessions(tmp_path):
    service = _make_service(tmp_path, "reset-isolation")
    service.session_repo.create(Session(id="s1", project_id="p1", title="会话1"))
    service.session_repo.create(Session(id="s2", project_id="p1", title="会话2"))
    _seed_turn_with_data(service, "s1", n=2)
    _seed_turn_with_data(service, "s2", n=2)

    service.reset_session("s1")

    assert service.turn_repo.list_by_session("s1") == []
    # s2 完好
    assert len(service.turn_repo.list_by_session("s2")) == 2
    assert len(service.run_repo.list_by_session("s2")) == 2
    assert service.session_repo.get("s2").last_event_seq > 0


def test_reset_session_not_found(tmp_path):
    service = _make_service(tmp_path, "reset-404")
    with pytest.raises(NotFoundValueError):
        service.reset_session("missing")


def test_reset_conflict_when_active_run_does_not_delete(tmp_path):
    service = _make_service(tmp_path, "reset-conflict")
    service.session_repo.create(Session(id="s1", project_id="p1", title="会话"))

    # 手工构造：turn.active_run_id 指向一个 RUNNING run，session.active_turn_id 指向该 turn。
    service.turn_repo.create(Turn(
        id="t1",
        session_id="s1",
        turn_index=0,
        root_message_id="m1",
        status=TurnStatus.RUNNING,
        active_run_id="r1",
    ))
    service.run_repo.create(Run(
        id="r1",
        session_id="s1",
        turn_id="t1",
        attempt_index=0,
        status=RunStatus.RUNNING,
    ))
    s = service.session_repo.get("s1")
    service.session_repo.update(s.model_copy(update={"active_turn_id": "t1"}))

    with pytest.raises(ValueError) as exc:
        service.reset_session("s1")
    assert not isinstance(exc.value, NotFoundValueError)

    # 冲突路径不删任何数据
    assert len(service.turn_repo.list_by_session("s1")) == 1
    assert len(service.run_repo.list_by_session("s1")) == 1
    assert service.session_repo.get("s1").active_turn_id == "t1"
