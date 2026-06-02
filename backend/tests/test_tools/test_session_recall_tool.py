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
