import pytest

from app.memory.recall_service import RecallService
from app.storage.database import Database
from app.tools.recall_tool import RecallTool


@pytest.fixture
def recall_service(tmp_path) -> RecallService:
    db = Database(str(tmp_path / "recall-tool.db"))
    service = RecallService(db=db)
    service.seed_document(
        message_id="msg-1",
        project_id="project-1",
        session_id="session-1",
        role="user",
        message_type="user_message",
        search_text="当前记忆部分应该是从messages表里面拿数据",
        turn_index=1,
        turn_message_index=1,
        created_at="2026-04-28T10:00:00",
    )
    return service


@pytest.fixture
def recall_tool(recall_service: RecallService) -> RecallTool:
    return RecallTool(recall_service=recall_service)


@pytest.mark.asyncio
async def test_recall_tool_returns_summary_and_evidence(recall_tool: RecallTool):
    result = await recall_tool.execute({"query": "messages 表", "project_id": "project-1", "limit": 3})
    assert result.success is True
    assert result.data is not None
    assert "results" in result.data
    assert "evidence" in result.data["results"][0]

