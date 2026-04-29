from app.execution.context_manager import LoopContext
from app.execution.plan_engine import Plan, PlanStep
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.tools.base import BaseTool, ToolResult
from app.tools.plan_tool import PlanTool
from app.tools.registry import ToolRegistry


class MockTool(BaseTool):
    @property
    def name(self) -> str:
        return "mock"

    @property
    def description(self) -> str:
        return "Mock tool"

    async def execute(self, args):
        return ToolResult(success=True, output="ok")


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(MockTool())
    registry.register(PlanTool())
    return registry


def test_initial_plan_definitions_expose_only_plan_create():
    definitions = RuntimeToolDefinitions(build_registry()).for_initial_plan()

    assert [definition.name for definition in definitions] == ["plan"]
    parameters_text = str(definitions[0].parameters)
    assert "create" in parameters_text
    assert "step_done" not in parameters_text


def test_normal_definitions_hide_plan_until_context_has_plan():
    context = LoopContext(task="解释函数")

    definitions = RuntimeToolDefinitions(build_registry()).for_context(context)

    assert [definition.name for definition in definitions] == ["mock"]


def test_normal_definitions_expose_plan_progress_without_create_when_plan_exists():
    context = LoopContext(task="修复 bug")
    context.plan = Plan(
        goal="修复 bug",
        steps=[PlanStep(id=1, description="定位问题")],
    )

    definitions = RuntimeToolDefinitions(build_registry()).for_context(context)

    assert [definition.name for definition in definitions] == ["mock", "plan"]
    plan_definition = next(definition for definition in definitions if definition.name == "plan")
    parameters_text = str(plan_definition.parameters)
    assert "step_done" in parameters_text
    assert "block" in parameters_text
    assert "adjust" in parameters_text
    assert "create" not in parameters_text
