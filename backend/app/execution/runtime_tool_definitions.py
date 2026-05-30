from __future__ import annotations

from typing import TYPE_CHECKING

from app.execution.context_manager import LoopContext
from app.llm.base import LLMToolDefinition
from app.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.tools.plan_tool import PlanTool


class RuntimeToolDefinitions:
    """Select the tool schemas exposed to the model for each execution phase."""

    EXPLORATION_TOOL_NAMES = {"file", "grep", "glob", "memory", "session_recall"}
    TOOL_ORDER = ["file", "grep", "glob", "session_recall", "memory", "edit", "shell"]

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    def for_initial_plan(self) -> list[LLMToolDefinition]:
        plan_tool = self.get_plan_tool()
        if plan_tool is None:
            return []
        return [self.tool_registry.definition_from_schema(plan_tool.get_create_schema())]

    def for_context(self, context: LoopContext) -> list[LLMToolDefinition]:
        from app.tools.plan_tool import PlanTool

        definitions: list[LLMToolDefinition] = []
        allowed_tool_names = self._allowed_tool_names(context)
        for name in self._ordered_tool_names():
            if name not in allowed_tool_names:
                continue
            tool = self.tool_registry.get(name)
            if tool is None:
                continue
            if isinstance(tool, PlanTool):
                if context.plan is not None:
                    definitions.append(
                        self.tool_registry.definition_from_schema(tool.get_progress_schema())
                    )
                continue
            definitions.append(self.tool_registry.definition_from_schema(tool.get_schema()))
        return definitions

    def _allowed_tool_names(self, context: LoopContext) -> set[str]:
        if context.steps:
            return set(self.tool_registry.list_tools())
        available = set(self.tool_registry.list_tools())
        exploration_tools = available.intersection(self.EXPLORATION_TOOL_NAMES)
        return exploration_tools or available

    def _ordered_tool_names(self) -> list[str]:
        names = self.tool_registry.list_tools()
        known = [name for name in self.TOOL_ORDER if name in names]
        unknown = [name for name in names if name not in self.TOOL_ORDER]
        return known + unknown

    def get_plan_tool(self) -> PlanTool | None:
        from app.tools.plan_tool import PlanTool

        tool = self.tool_registry.get("plan")
        return tool if isinstance(tool, PlanTool) else None
