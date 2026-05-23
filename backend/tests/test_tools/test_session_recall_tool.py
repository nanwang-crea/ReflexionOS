import pytest

from app.tools.session_recall_tool import SessionRecallTool


def test_session_recall_tool_name():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    assert tool.name == "session_recall"


def test_session_recall_tool_schema():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    schema = tool.get_schema()
    assert "query" in schema["parameters"]["properties"]


@pytest.mark.asyncio
async def test_session_recall_tool_execute_empty_query():
    tool = SessionRecallTool(session_id="s1", project_id="p1")
    result = await tool.execute({"query": ""})
    assert result.success is True
    assert result.data is not None
