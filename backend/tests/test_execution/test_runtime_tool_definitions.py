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


class GrepLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "grep"


class GlobLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "glob"


class FileLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "file"


class EditLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "edit"


class ShellLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "shell"


class MemoryLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "memory"


class SessionRecallLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "session_recall"


class SkillLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "skill"


class ExploreLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "explore"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(MockTool())
    registry.register(PlanTool())
    return registry




def test_normal_definitions_expose_plan_schema_when_no_plan_exists():
    context = LoopContext(task="解释函数")

    definitions = RuntimeToolDefinitions(build_registry()).for_context(context)

    names = [definition.name for definition in definitions]
    assert "plan" in names
    plan_definition = next(d for d in definitions if d.name == "plan")
    parameters = plan_definition.parameters
    assert "steps" in parameters.get("properties", {})
    assert "goal" in parameters.get("properties", {})


def test_normal_definitions_expose_plan_schema_when_plan_exists():
    context = LoopContext(task="修复 bug")
    context.plan = Plan(
        goal="修复 bug",
        steps=[PlanStep(content="定位问题", status="in_progress")],
    )

    definitions = RuntimeToolDefinitions(build_registry()).for_context(context)

    assert [definition.name for definition in definitions] == ["mock", "plan"]
    plan_definition = next(
        definition for definition in definitions if definition.name == "plan"
    )
    parameters = plan_definition.parameters
    assert "steps" in parameters.get("properties", {})
    assert "goal" in parameters.get("properties", {})


def test_context_definitions_start_with_exploration_tools_only():
    registry = ToolRegistry()
    registry.register(FileLikeTool())
    registry.register(GrepLikeTool())
    registry.register(GlobLikeTool())
    registry.register(EditLikeTool())
    registry.register(ShellLikeTool())
    registry.register(MemoryLikeTool())
    registry.register(SkillLikeTool())
    context = LoopContext(task="先看看项目")

    definitions = RuntimeToolDefinitions(registry).for_context(context)

    assert [definition.name for definition in definitions] == [
        "skill",
        "file",
        "grep",
        "glob",
        "memory",
    ]


def build_plan_mode_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(FileLikeTool())
    registry.register(GrepLikeTool())
    registry.register(GlobLikeTool())
    registry.register(MemoryLikeTool())
    registry.register(SessionRecallLikeTool())
    registry.register(ExploreLikeTool())
    registry.register(PlanTool())
    return registry


def test_plan_mode_definitions_expose_plan_schema():
    definitions = RuntimeToolDefinitions(build_plan_mode_registry()).for_plan_mode()

    names = [definition.name for definition in definitions]
    assert "plan" in names

    plan_definition = next(d for d in definitions if d.name == "plan")
    parameters = plan_definition.parameters
    assert "steps" in parameters.get("properties", {})
    assert "goal" in parameters.get("properties", {})


def test_plan_mode_definitions_only_include_plan_mode_tools():
    definitions = RuntimeToolDefinitions(build_plan_mode_registry()).for_plan_mode()

    names = [definition.name for definition in definitions]
    assert "edit" not in names
    assert "shell" not in names


def test_skill_tool_available_on_first_turn():
    from app.execution.runtime_tool_definitions import DEFAULT_TOOL_SET_CONFIG

    assert "skill" in DEFAULT_TOOL_SET_CONFIG.exploration_tools


def test_skill_tool_in_tool_order():
    from app.execution.runtime_tool_definitions import DEFAULT_TOOL_SET_CONFIG

    assert "skill" in DEFAULT_TOOL_SET_CONFIG.tool_order
    assert DEFAULT_TOOL_SET_CONFIG.tool_order.index("skill") == 0


def test_context_definitions_expose_mutating_tools_after_exploration_started():
    registry = ToolRegistry()
    registry.register(FileLikeTool())
    registry.register(GrepLikeTool())
    registry.register(GlobLikeTool())
    registry.register(EditLikeTool())
    registry.register(ShellLikeTool())
    context = LoopContext(task="修复问题")
    context.add_step(type("Step", (), {"step_number": 1, "tool": "grep"})())

    definitions = RuntimeToolDefinitions(registry).for_context(context)

    assert [definition.name for definition in definitions] == [
        "file",
        "grep",
        "glob",
        "edit",
        "shell",
    ]
