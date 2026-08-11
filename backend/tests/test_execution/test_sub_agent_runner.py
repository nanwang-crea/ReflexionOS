from types import SimpleNamespace

import pytest

import app.agents.sub_agent_runner as sub_agent_runner_module
from app.agents.sub_agent_runner import SubAgentRunner
from app.execution.models import LoopResult, LoopStatus
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.path_security import PathSecurity
from app.security.sandbox.factory import NullSandbox
from app.security.shell_security import ShellSecurity
from app.tools.base import BaseTool, ToolResult
from app.agents.sub_agent_runner import _build_filtered_registry
from app.tools.delegate_tool import DelegateTool
from app.tools.plan_tool import PlanTool
from app.tools.registry import ToolRegistry
from app.tools.shell_tool import ShellTool
from app.tools.working_memory_tool import WorkingMemoryTool


class DummyTool(BaseTool):
    def __init__(self, tool_name: str):
        self._tool_name = tool_name

    @property
    def name(self) -> str:
        return self._tool_name

    @property
    def description(self) -> str:
        return self._tool_name

    def get_schema(self):
        return {"name": self.name, "description": self.description, "parameters": {"type": "object"}}

    async def execute(self, args: dict):
        return ToolResult(success=True, output="")


def test_filtered_sub_agent_registry_excludes_delegate():
    registry = ToolRegistry()
    registry.register(
        DelegateTool(
            runner_factory=lambda **_: None,
        )
    )
    registry.register(WorkingMemoryTool())

    filtered = _build_filtered_registry(registry)

    assert filtered.get("delegate") is None
    assert filtered.get("working_memory_update") is not None


def test_filtered_sub_agent_registry_excludes_plan_and_browser():
    registry = ToolRegistry()
    registry.register(DummyTool("plan"))
    registry.register(DummyTool("browser"))

    filtered = _build_filtered_registry(registry)

    assert filtered.get("plan") is None
    assert filtered.get("browser") is None


def test_filtered_sub_agent_registry_isolates_stateful_tools():
    parent_working_memory = WorkingMemoryTool()
    registry = ToolRegistry()
    registry.register(parent_working_memory)
    registry.register(PlanTool())

    first = _build_filtered_registry(registry)
    second = _build_filtered_registry(registry)

    assert first.get("working_memory_update") is not parent_working_memory
    assert second.get("working_memory_update") is not parent_working_memory
    assert first.get("working_memory_update") is not second.get("working_memory_update")
    assert first.get("plan") is None
    assert second.get("plan") is None


def test_filtered_sub_agent_registry_rebinds_shell_session_id(tmp_path):
    root_dir = str(tmp_path)
    path_security = PathSecurity([root_dir], base_dir=root_dir)
    parent_shell = ShellTool(
        ShellSecurity(),
        path_security,
        CommandEffectRegistry(),
        NullSandbox(),
        session_id="parent-session",
    )
    registry = ToolRegistry()
    registry.register(parent_shell)

    filtered = _build_filtered_registry(registry, session_id="child-session")
    child_shell = filtered.get("shell")

    assert child_shell is not None
    assert child_shell is not parent_shell
    assert child_shell._session_id == "child-session"


@pytest.mark.asyncio
async def test_sub_agent_runner_reports_loop_lifecycle(monkeypatch):
    registry = ToolRegistry()
    events: list[tuple[str, str, object]] = []

    class FakeLoop:
        def __init__(self, **kwargs):
            self.tool_registry = kwargs["tool_registry"]

        async def run(self, **kwargs):
            return LoopResult(
                id=kwargs["run_id"],
                task=kwargs["task"],
                status=LoopStatus.COMPLETED,
                result="done",
                steps=[],
            )

    monkeypatch.setattr(
        sub_agent_runner_module.LLMAdapterFactory,
        "create",
        lambda config: SimpleNamespace(),
    )
    monkeypatch.setattr(sub_agent_runner_module, "RapidExecutionLoop", FakeLoop)

    runner = SubAgentRunner(
        task="检查生命周期",
        llm_config=SimpleNamespace(),
        parent_tool_registry=registry,
        loop_started=lambda run_id, loop: events.append(("start", run_id, loop)),
        loop_finished=lambda run_id, loop: events.append(("finish", run_id, loop)),
    )

    result = await runner.run()

    assert result.status == "completed"
    assert result.output == "done"
    assert [event[0] for event in events] == ["start", "finish"]
    assert events[0][1].startswith("sub-run-")
    assert events[1][1] == events[0][1]
    assert events[1][2] is events[0][2]
