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
            "working_memory_update",
            "edit",
            "shell",
            "delegate",
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
                "working_memory_update",
                "plan",
                "delegate",
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
    # sub-agent 模式下排除的工具名（防止递归调用 delegate 等）
    sub_agent_tools: frozenset[str] = field(default_factory=frozenset)
    # 跳过首轮"探索工具收窄"门禁：子 agent 任务通常已明确要执行的操作（如 shell 命令），
    # 不需要像主 Agent 一样先观察后行动，首轮就应看到完整工具集
    skip_exploration_gate: bool = False


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
        # 先排除 sub_agent_tools 中的工具（如 delegate 在 sub-agent 模式下）
        exclude = self.config.sub_agent_tools
        available = set(self.tool_registry.list_tools_excluding(exclude))
        # 已执行过步骤，或配置为跳过首轮探索门禁（子 agent 场景）：直接给全量工具
        if context.steps or self.config.skip_exploration_gate:
            return available
        exploration_tools = available.intersection(self.config.exploration_tools)
        return exploration_tools or available

    def _ordered_tool_names(self) -> list[str]:
        # 使用 list_tools_excluding 排除 sub_agent_tools
        names = self.tool_registry.list_tools_excluding(self.config.sub_agent_tools)
        known = [name for name in self.config.tool_order if name in names]
        unknown = [name for name in names if name not in self.config.tool_order]
        return known + unknown

    def get_plan_tool(self) -> PlanTool | None:
        from app.tools.plan_tool import PlanTool

        tool = self.tool_registry.get("plan")
        return tool if isinstance(tool, PlanTool) else None
