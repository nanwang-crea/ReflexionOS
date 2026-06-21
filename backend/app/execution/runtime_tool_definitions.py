from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.execution.context_manager import LoopContext
from app.llm.base import LLMToolDefinition
from app.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.tools.plan_tool import PlanTool


@dataclass(frozen=True)
class ToolSetConfig:
    tool_order: list[str] = field(
        default_factory=lambda: [
            "skill",
            "file",
            "grep",
            "glob",
            "session_recall",
            "memory",
            "edit",
            "shell",
        ]
    )
    exploration_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "file",
                "grep",
                "glob",
                "memory",
                "session_recall",
                "skill",
            }
        )
    )
    plan_mode_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "file",
                "grep",
                "glob",
                "session_recall",
                "memory",
                "explore",
                "plan",
            }
        )
    )


DEFAULT_TOOL_SET_CONFIG = ToolSetConfig()


class RuntimeToolDefinitions:
    """Select the tool schemas exposed to the model for each execution phase."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        config: ToolSetConfig = DEFAULT_TOOL_SET_CONFIG,
    ):
        self.tool_registry = tool_registry
        self.config = config

    def for_initial_plan(self) -> list[LLMToolDefinition]:
        plan_tool = self.get_plan_tool()
        if plan_tool is None:
            return []
        return [self.tool_registry.definition_from_schema(plan_tool.get_schema())]

    def for_plan_mode(self) -> list[LLMToolDefinition]:
        definitions: list[LLMToolDefinition] = []
        for name in self._ordered_tool_names():
            if name not in self.config.plan_mode_tools:
                continue
            tool = self.tool_registry.get(name)
            if tool is None:
                continue
            definitions.append(
                self.tool_registry.definition_from_schema(tool.get_schema())
            )

        return definitions

    def for_context(self, context: LoopContext) -> list[LLMToolDefinition]:

        definitions: list[LLMToolDefinition] = []
        allowed_tool_names = self._allowed_tool_names(context)
        for name in self._ordered_tool_names():
            if name not in allowed_tool_names:
                continue
            tool = self.tool_registry.get(name)
            if tool is None:
                continue
            definitions.append(
                self.tool_registry.definition_from_schema(tool.get_schema())
            )
        return definitions

    def _allowed_tool_names(self, context: LoopContext) -> set[str]:
        if context.steps:
            return set(self.tool_registry.list_tools())
        available = set(self.tool_registry.list_tools())
        exploration_tools = available.intersection(self.config.exploration_tools)
        return exploration_tools or available

    def _ordered_tool_names(self) -> list[str]:
        names = self.tool_registry.list_tools()
        known = [name for name in self.config.tool_order if name in names]
        unknown = [name for name in names if name not in self.config.tool_order]
        return known + unknown

    def get_plan_tool(self) -> PlanTool | None:
        from app.tools.plan_tool import PlanTool

        tool = self.tool_registry.get("plan")
        return tool if isinstance(tool, PlanTool) else None
