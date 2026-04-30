import pytest

from app.tools.plan_tool import PlanTool


def assert_openai_compatible_parameters(schema):
    parameters = schema["parameters"]
    assert parameters["type"] == "object"
    assert "oneOf" not in parameters
    assert "anyOf" not in parameters
    assert "allOf" not in parameters
    assert "not" not in parameters
    assert "enum" not in parameters


async def create_plan(tool: PlanTool, steps):
    return await tool.execute({
        "action": "create",
        "goal": "修复计划显示",
        "steps": steps,
    })


def test_plan_schemas_do_not_use_top_level_composition_keywords():
    tool = PlanTool()

    assert_openai_compatible_parameters(tool.get_schema())
    assert_openai_compatible_parameters(tool.get_create_schema())
    assert_openai_compatible_parameters(tool.get_progress_schema())


def test_plan_create_schema_is_flat_and_requires_create_inputs():
    schema = PlanTool().get_create_schema()
    parameters = schema["parameters"]

    assert parameters["required"] == ["action", "goal", "steps"]
    assert parameters["properties"]["action"]["enum"] == ["create"]
    assert "steps" in parameters["properties"]


def test_plan_progress_schema_is_flat_and_does_not_expose_create():
    schema = PlanTool().get_progress_schema()
    parameters = schema["parameters"]

    assert parameters["required"] == ["action"]
    assert parameters["properties"]["action"]["enum"] == ["step_done", "block", "adjust"]
    assert "goal" not in parameters["properties"]
    assert "steps" not in parameters["properties"]


@pytest.mark.asyncio
async def test_plan_create_parses_json_encoded_steps_array():
    tool = PlanTool()

    result = await create_plan(tool, '["分析当前问题", "修改计划工具", "验证显示结果"]')

    assert result.success is True
    assert [step["description"] for step in result.data["steps"]] == [
        "分析当前问题",
        "修改计划工具",
        "验证显示结果",
    ]


@pytest.mark.asyncio
async def test_plan_create_rejects_plain_string_steps_instead_of_splitting_characters():
    tool = PlanTool()

    result = await create_plan(tool, "分析当前问题")

    assert result.success is False
    assert "steps 必须是字符串数组" in result.error
    assert tool.get_plan() is None


@pytest.mark.asyncio
async def test_plan_step_done_requires_findings_after_flattening_schema():
    tool = PlanTool()
    await create_plan(tool, ["定位问题", "验证结果"])

    result = await tool.execute({"action": "step_done"})

    assert result.success is False
    assert "需要 findings 参数" in result.error
    assert tool.get_plan().current_step.description == "定位问题"


@pytest.mark.asyncio
async def test_plan_block_requires_reason_after_flattening_schema():
    tool = PlanTool()
    await create_plan(tool, ["定位问题"])

    result = await tool.execute({"action": "block"})

    assert result.success is False
    assert "需要 reason 参数" in result.error
    assert tool.get_plan().current_step.status == "in_progress"


@pytest.mark.asyncio
async def test_plan_adjust_requires_remaining_steps_array_after_flattening_schema():
    tool = PlanTool()
    await create_plan(tool, ["定位问题", "验证结果"])

    result = await tool.execute({
        "action": "adjust",
        "remaining_steps": "验证结果",
    })

    assert result.success is False
    assert "remaining_steps 必须是字符串数组" in result.error
    assert [step.description for step in tool.get_plan().steps] == ["定位问题", "验证结果"]
