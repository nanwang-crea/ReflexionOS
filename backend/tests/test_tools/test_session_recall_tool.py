import pytest

from app.tools.session_recall_tool import SessionRecallTool


def test_session_recall_tool_name():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    assert tool.name == "session_recall"


def test_session_recall_tool_schema():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    schema = tool.get_schema()
    assert "query" in schema["parameters"]["properties"]
    assert "query" in schema["parameters"]["required"]


@pytest.mark.asyncio
async def test_session_recall_tool_execute_empty_query_returns_error():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    result = await tool.execute({"query": ""})
    assert result.success is False
    assert result.error is not None
    assert "required" in result.error.lower()


@pytest.mark.asyncio
async def test_session_recall_tool_execute_no_query_returns_error():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    result = await tool.execute({})
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_session_recall_tool_execute_returns_output_field():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    result = await tool.execute({"query": "test"})
    assert result.output is not None
    assert isinstance(result.output, str)


@pytest.mark.asyncio
async def test_session_recall_tool_no_results_has_output():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    result = await tool.execute({"query": "nonexistent_query_xyz"})
    assert result.output is not None
    assert "no results" in result.output.lower() or result.output == ""


# ---------------------------------------------------------------------------
# 项目级跨会话召回（scope="project"）
# ---------------------------------------------------------------------------
from app.memory.recall_service import RecallResult  # noqa: E402


class FakeRecallService:
    """记录 search 入参并返回预置结果的假检索服务。"""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, *, project_id, query, limit=3, session_id=None):
        self.calls.append({"project_id": project_id, "query": query, "limit": limit, "session_id": session_id})
        return self.results


def _result(session_id: str, summary: str) -> RecallResult:
    return RecallResult(message_id="m1", session_id=session_id, score=0.8, summary=summary, evidence=["  ev1"])


@pytest.mark.asyncio
async def test_project_scope_searches_all_project_sessions_and_labels_sources():
    fake = FakeRecallService([_result("s-old", "早前会话读过 auth.py"), _result("s1", "本会话内容")])
    tool = SessionRecallTool(session_id="s1", project_id="p1", recall_service=fake)

    result = await tool.execute({"query": "auth.py", "scope": "project"})

    assert result.success is True
    assert fake.calls[0]["session_id"] is None  # 项目级：不限定会话
    assert result.data["scope"] == "project"
    assert [r["session_id"] for r in result.data["results"]] == ["s-old", "s1"]
    assert "[session s-old]" in result.output


@pytest.mark.asyncio
async def test_session_scope_default_limits_to_current_session():
    fake = FakeRecallService([_result("s1", "本会话内容")])
    tool = SessionRecallTool(session_id="s1", project_id="p1", recall_service=fake)

    result = await tool.execute({"query": "auth"})

    assert result.success is True
    assert fake.calls[0]["session_id"] == "s1"
    assert result.data["scope"] == "session"
    assert "[session" not in result.output  # 会话级输出不带来源标注（保持兼容）


@pytest.mark.asyncio
async def test_invalid_scope_returns_error():
    tool = SessionRecallTool(session_id="s1", project_id="p1", recall_service=FakeRecallService([]))
    result = await tool.execute({"query": "x", "scope": "global"})
    assert result.success is False
    assert "scope" in (result.error or "")


def test_schema_exposes_scope_param():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    schema = tool.get_schema()
    assert schema["parameters"]["properties"]["scope"]["enum"] == ["session", "project"]
