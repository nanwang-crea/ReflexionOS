import pytest

from app.tools.plan_tool import PlanTool


async def create_plan(tool: PlanTool, steps):
    return await tool.execute({
        "action": "create",
        "goal": "修复计划显示",
        "steps": steps,
    })


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
