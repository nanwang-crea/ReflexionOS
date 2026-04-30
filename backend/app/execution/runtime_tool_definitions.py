from __future__ import annotations

from app.execution.context_manager import LoopContext
from app.llm.base import LLMToolDefinition
from app.tools.registry import ToolRegistry


class RuntimeToolDefinitions:
    """Select the tool schemas exposed to the model for each execution phase."""

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
        for name in self.tool_registry.list_tools():
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

    def get_plan_tool(self) -> PlanTool | None:
        from app.tools.plan_tool import PlanTool

        tool = self.tool_registry.get("plan")
        return tool if isinstance(tool, PlanTool) else None
