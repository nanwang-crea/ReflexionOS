import pytest
from app.tools.plan_tool import PlanTool


@pytest.fixture
def tool():
    return PlanTool()


def test_plan_schema_is_flat_and_single_action(tool):
    schema = tool.get_schema()
    params = schema["parameters"]
    assert "action" not in params["properties"]
    assert "steps" in params["properties"]
    assert "goal" in params["properties"]
    assert params["required"] == ["steps"]


def test_plan_schema_steps_items_have_content_status_findings(tool):
    schema = tool.get_schema()
    step_props = schema["parameters"]["properties"]["steps"]["items"]["properties"]
    assert "content" in step_props
    assert "status" in step_props
    assert step_props["status"]["enum"] == ["pending", "in_progress", "completed", "blocked"]
    assert "findings" in step_props


@pytest.mark.asyncio
async def test_plan_create_on_first_call(tool):
    result = await tool.execute({
        "goal": "Fix auth bug",
        "steps": [
            {"content": "Analyze", "status": "in_progress"},
            {"content": "Fix", "status": "pending"},
        ],
    })
    assert result.success
    assert "Plan updated" in result.output
    plan = tool.get_plan()
    assert plan is not None
    assert plan.goal == "Fix auth bug"
    assert len(plan.steps) == 2
    assert plan.current_step.content == "Analyze"


@pytest.mark.asyncio
async def test_plan_full_replace_on_subsequent_call(tool):
    await tool.execute({
        "goal": "Fix auth",
        "steps": [
            {"content": "Analyze", "status": "in_progress"},
            {"content": "Fix", "status": "pending"},
        ],
    })
    result = await tool.execute({
        "steps": [
            {"content": "Analyze", "status": "completed", "findings": "Found bug"},
            {"content": "Fix", "status": "in_progress"},
            {"content": "Test", "status": "pending"},
        ],
    })
    assert result.success
    plan = tool.get_plan()
    assert plan.steps[0].status == "completed"
    assert plan.steps[1].status == "in_progress"
    assert len(plan.steps) == 3


@pytest.mark.asyncio
async def test_plan_rejects_goal_missing_on_first_call(tool):
    result = await tool.execute({
        "steps": [{"content": "Do something", "status": "pending"}],
    })
    assert not result.success
    assert "goal" in result.error.lower()


@pytest.mark.asyncio
async def test_plan_rejects_multiple_in_progress(tool):
    await tool.execute({
        "goal": "Test",
        "steps": [{"content": "A", "status": "in_progress"}],
    })
    result = await tool.execute({
        "steps": [
            {"content": "A", "status": "in_progress"},
            {"content": "B", "status": "in_progress"},
        ],
    })
    assert not result.success
    assert "in_progress" in result.error.lower()


@pytest.mark.asyncio
async def test_plan_completed_step_requires_findings(tool):
    await tool.execute({
        "goal": "Test",
        "steps": [{"content": "A", "status": "in_progress"}],
    })
    result = await tool.execute({
        "steps": [{"content": "A", "status": "completed"}],
    })
    assert not result.success


@pytest.mark.asyncio
async def test_plan_returns_metadata(tool):
    await tool.execute({
        "goal": "Test",
        "steps": [
            {"content": "A", "status": "in_progress"},
            {"content": "B", "status": "pending"},
        ],
    })
    result = await tool.execute({
        "steps": [
            {"content": "A", "status": "completed", "findings": "Done"},
            {"content": "B", "status": "in_progress"},
        ],
    })
    assert result.success
    data = result.data
    assert data["is_new"] is False
    assert data["just_completed"] == ["A"]
    assert data["just_started"] == "B"
    assert data["completed"] == 1
    assert data["total"] == 2


def test_plan_no_create_or_progress_schema_methods(tool):
    assert not hasattr(tool, "get_create_schema")
    assert not hasattr(tool, "get_progress_schema")


def test_plan_set_and_get_plan(tool):
    from app.execution.plan_engine import Plan, PlanStep
    plan = Plan(goal="Test", steps=[PlanStep(content="S1", status="pending")])
    tool.set_plan(plan)
    assert tool.get_plan() is plan
    tool.set_plan(None)
    assert tool.get_plan() is None
