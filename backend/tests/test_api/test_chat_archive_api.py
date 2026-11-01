"""会话归档（.reflexion-chat.json）导出/导入 API 的集成测试。

覆盖：
- 导出：正常折叠（format/version/角色/工具挂载）、运行中拒绝、空会话拒绝；
- 导入：重建为新会话（事件/轮次/工具轨迹/运行终态）、非法结构 400 且无残留会话、
  项目不存在 404、超过 16MiB 上限 400。
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ids import new_event_id, new_message_id
from app.main import app
from app.llm.base import MessageRole
from app.models.conversation import ConversationEvent, EventType
from app.models.llm_config import ProviderType, ResolvedLLMConfig
from app.models.project import Project
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.services.llm_provider_service import LLMProviderService
from app.services.session_service import SessionService
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


@pytest.fixture
def archive_env(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "archive.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(tmp_path)))
    session_repo.create(Session(id="session-1", project_id="project-1", title="待导出会话"))

    conversation_service = ConversationService(db=db)
    session_service = SessionService(db=db, session_repo=session_repo, project_repo=project_repo)

    import app.api.routes.sessions as sessions_route_module

    monkeypatch.setattr(sessions_route_module, "conversation_service", conversation_service)
    monkeypatch.setattr(sessions_route_module, "session_service", session_service)

    with TestClient(app) as test_client:
        yield test_client, conversation_service, session_service, session_repo


def _seed_completed_exchange(conversation_service, *, session_id: str) -> None:
    """播种一轮完整对话：用户消息 + 运行 + 助手回复 + 一条工具轨迹，全部终态。"""
    started = conversation_service.start_turn(
        session_id=session_id,
        content="帮我看看仓库",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    turn_id = started.turn.id
    run_id = started.run.id
    tool_message_id = new_message_id()
    assistant_message_id = new_message_id()
    # 工具与助手在同批事件里落库，必须各自分配互不相同的 turn_message_index
    # （先取工具号，助手号顺延）；本批末尾的 RUN_COMPLETED 是该 run 的合法终态迁移
    tool_index = conversation_service.next_message_index(turn_id)
    assistant_index = tool_index + 1
    conversation_service.append_events(
        session_id,
        [
            ConversationEvent(
                id=new_event_id(),
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                message_id=tool_message_id,
                event_type=EventType.MESSAGE_CREATED,
                payload_json={
                    "message_id": tool_message_id,
                    "turn_id": turn_id,
                    "run_id": run_id,
                    "role": MessageRole.TOOL,
                    "message_type": "tool_trace",
                    "turn_message_index": tool_index,
                    "display_mode": "default",
                    "content_text": "",
                    "payload_json": {
                        "tool_name": "grep",
                        "arguments": {"pattern": "main"},
                        "tool_call_id": "call-1",
                        "output": "main.py:1",
                        "status": "completed",
                    },
                },
            ),
            ConversationEvent(
                id=new_event_id(),
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                message_id=tool_message_id,
                event_type=EventType.MESSAGE_COMPLETED,
                payload_json={"completed_at": "2026-11-01T10:00:05"},
            ),
            ConversationEvent(
                id=new_event_id(),
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                message_id=assistant_message_id,
                event_type=EventType.MESSAGE_CREATED,
                payload_json={
                    "message_id": assistant_message_id,
                    "turn_id": turn_id,
                    "run_id": run_id,
                    "role": MessageRole.ASSISTANT,
                    "message_type": "assistant_message",
                    "turn_message_index": assistant_index,
                    "display_mode": "default",
                    "content_text": "仓库入口在 main.py",
                    "payload_json": {"reasoning_text": "先搜索再总结"},
                    "attachments": [],
                },
            ),
            ConversationEvent(
                id=new_event_id(),
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                message_id=assistant_message_id,
                event_type=EventType.MESSAGE_COMPLETED,
                payload_json={"completed_at": "2026-11-01T10:00:06"},
            ),
            ConversationEvent(
                id=new_event_id(),
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                event_type=EventType.RUN_COMPLETED,
                payload_json={"finished_at": "2026-11-01T10:00:07"},
            ),
        ],
    )


def test_export_folds_session_into_reflexion_chat_archive(archive_env):
    client, conversation_service, _, _ = archive_env
    _seed_completed_exchange(conversation_service, session_id="session-1")

    response = client.get("/api/sessions/session-1/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    archive = json.loads(response.content.decode("utf-8"))
    assert archive["format"] == "reflexion-chat"
    assert archive["version"] == 1
    assert archive["title"] == "待导出会话"
    roles = [entry["role"] for entry in archive["messages"]]
    assert roles == ["user", "assistant"]
    assistant_entry = archive["messages"][1]
    assert assistant_entry["content"] == "仓库入口在 main.py"
    assert assistant_entry["reasoning"] == "先搜索再总结"
    assert [tool["name"] for tool in assistant_entry["tools"]] == ["grep"]
    assert assistant_entry["tools"][0]["output"] == "main.py:1"


def test_export_rejects_session_with_active_run(archive_env):
    client, conversation_service, _, _ = archive_env
    conversation_service.start_turn(
        session_id="session-1",
        content="运行中",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    response = client.get("/api/sessions/session-1/export")

    assert response.status_code == 400
    assert "运行中" in json.dumps(response.json(), ensure_ascii=False)


def test_export_rejects_empty_session(archive_env):
    client, _, _, _ = archive_env

    response = client.get("/api/sessions/session-1/export")

    assert response.status_code == 400


def test_import_rebuilds_session_with_lazy_tool_records(archive_env):
    client, conversation_service, _, session_repo = archive_env
    archive = {
        "format": "reflexion-chat",
        "version": 1,
        "title": "导入来源",
        "messages": [
            {"role": "user", "content": "上一台机器的问题", "created_at": "2026-10-01T09:00:00"},
            {
                "role": "assistant",
                "content": "已经修好了",
                "status": "completed",
                "model": "model-a",
                "created_at": "2026-10-01T09:01:00",
                "tools": [
                    {"name": "edit", "arguments": {"path": "/x.py"}, "output": "成功替换", "status": "completed"}
                ],
            },
        ],
    }

    response = client.post(
        "/api/sessions/import",
        files={"file": ("reflexion-chat.json", json.dumps(archive).encode("utf-8"), "application/json")},
        data={"project_id": "project-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_messages"] == 2
    assert body["imported_tools"] == 1
    new_session_id = body["session_id"]
    assert body["title"].endswith("（导入）")

    # 会话确实创建在目标项目下
    session_ids = {session.id for session in session_repo.list_by_project("project-1")}
    assert new_session_id in session_ids

    snapshot = conversation_service.get_snapshot(new_session_id)
    assert len(snapshot.turns) == 1
    assert [message.message_type.value for message in snapshot.messages] == [
        "user_message",
        "tool_trace",
        "assistant_message",
    ]
    assert snapshot.messages[0].content_text == "上一台机器的问题"
    assert snapshot.messages[1].payload_json["tool_name"] == "edit"
    assert snapshot.messages[1].payload_json["status"] == "completed"
    assert snapshot.messages[2].content_text == "已经修好了"
    # 运行终态收尾
    assert snapshot.runs[0].status.value == "completed"


def test_import_invalid_structure_returns_400_and_leaves_no_session(archive_env):
    client, _, _, session_repo = archive_env
    before = {session.id for session in session_repo.list_by_project("project-1")}

    bad_archive = {"format": "reflexion-chat", "version": 1, "messages": [{"role": "system", "content": "x"}]}
    response = client.post(
        "/api/sessions/import",
        files={"file": ("bad.json", json.dumps(bad_archive).encode("utf-8"), "application/json")},
        data={"project_id": "project-1"},
    )

    assert response.status_code == 400
    body = response.json()
    assert "role 非法" in json.dumps(body, ensure_ascii=False)
    after = {session.id for session in session_repo.list_by_project("project-1")}
    assert after == before


def test_import_to_missing_project_returns_404(archive_env):
    client, _, _, _ = archive_env
    archive = {
        "format": "reflexion-chat",
        "version": 1,
        "title": "t",
        "messages": [{"role": "user", "content": "hello"}],
    }

    response = client.post(
        "/api/sessions/import",
        files={"file": ("ok.json", json.dumps(archive).encode("utf-8"), "application/json")},
        data={"project_id": "project-missing"},
    )

    assert response.status_code == 404


def test_import_rejects_oversized_archive(archive_env):
    client, _, _, _ = archive_env
    big_payload = b'{"format":"reflexion-chat","version":1,"messages":[]}' + b" " * (17 * 1024 * 1024)

    response = client.post(
        "/api/sessions/import",
        files={"file": ("big.json", big_payload, "application/json")},
        data={"project_id": "project-1"},
    )

    assert response.status_code == 400
