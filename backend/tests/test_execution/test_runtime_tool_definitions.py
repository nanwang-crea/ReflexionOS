from app.execution.context_manager import LoopContext
from app.execution.plan_engine import Plan, PlanStep
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.tools.base import BaseTool, ToolResult
from app.tools.plan_exit_tool import PlanExitTool
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


class ExploreLikeTool(MockTool):
    @property
    def name(self) -> str:
        return "explore"


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


def test_context_definitions_start_with_exploration_tools_only():
    registry = ToolRegistry()
    registry.register(FileLikeTool())
    registry.register(GrepLikeTool())
    registry.register(GlobLikeTool())
    registry.register(EditLikeTool())
    registry.register(ShellLikeTool())
    registry.register(MemoryLikeTool())
    context = LoopContext(task="先看看项目")

    definitions = RuntimeToolDefinitions(registry).for_context(context)

    assert [definition.name for definition in definitions] == ["file", "grep", "glob", "memory"]


def build_plan_mode_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(FileLikeTool())
    registry.register(GrepLikeTool())
    registry.register(GlobLikeTool())
    registry.register(MemoryLikeTool())
    registry.register(SessionRecallLikeTool())
    registry.register(ExploreLikeTool())
    registry.register(PlanTool())
    registry.register(PlanExitTool())
    return registry


def test_plan_mode_definitions_expose_plan_create_and_plan_exit():
    definitions = RuntimeToolDefinitions(build_plan_mode_registry()).for_plan_mode()

    names = [definition.name for definition in definitions]
    assert "plan" in names
    assert "plan_exit" in names

    plan_definition = next(d for d in definitions if d.name == "plan")
    parameters_text = str(plan_definition.parameters)
    assert "create" in parameters_text
    assert "step_done" not in parameters_text


def test_plan_mode_definitions_only_include_plan_mode_tools():
    definitions = RuntimeToolDefinitions(build_plan_mode_registry()).for_plan_mode()

    names = [definition.name for definition in definitions]
    assert "edit" not in names
    assert "shell" not in names


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
