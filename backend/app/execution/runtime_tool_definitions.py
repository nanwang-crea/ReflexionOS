"""
文件功能：为每个执行阶段选择应暴露给模型的工具集合
文件描述：定义 ToolSetConfig（声明工具展示顺序、探索类工具白名单、PLAN 模式工具白名单、
         SubAgent 场景需要排除的工具）与 RuntimeToolDefinitions（依据配置和当前执行上下文，
         从 ToolRegistry 中筛选、排序并转换为 LLM 可用的工具 schema 列表）。
核心逻辑：核心是"首轮探索门禁"——一次运行还没有执行过任何步骤时，只暴露只读探索类工具
         （file/grep/glob/memory 等），迫使 LLM 先观察后行动，避免上来就贸然写操作；
         一旦已执行过步骤（或配置显式跳过该门禁，如 SubAgent 场景），则放开完整工具集。
         PLAN 模式和 SubAgent 场景各自有独立的工具白名单/排除名单，通过 ToolSetConfig
         灵活配置，不需要修改本文件逻辑。
"""

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
    """
    工具集配置，决定不同执行场景下模型可见的工具范围。
    字段说明：
      - tool_order：工具在最终列表中的展示/排序优先级（未列出的工具追加在后面）
      - exploration_tools：首轮"探索门禁"阶段允许暴露的只读/低风险工具白名单
      - plan_mode_tools：PLAN 模式（只规划不落地）下允许暴露的工具白名单
      - sub_agent_tools：SubAgent 模式下需要排除的工具名（防止递归调用 delegate 等）
      - skip_exploration_gate：是否跳过首轮探索门禁；SubAgent 任务目标通常已明确，
                               不需要像主 Agent 一样先观察后行动
    """

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
        """
        函数名：__init__
        入参：
          - tool_registry (ToolRegistry)：工具注册表，提供全部已注册工具的查询能力
          - config (ToolSetConfig)：工具集配置，决定不同场景下的可见工具范围，默认使用
                                     全局默认配置
        功能：初始化工具定义选择器
        运行逻辑：直接保存 tool_registry 与 config 引用
        出参：无
        """
        self.tool_registry = tool_registry
        self.config = config

    def for_plan_mode(self) -> list[LLMToolDefinition]:
        """
        函数名：for_plan_mode
        入参：无
        功能：获取 PLAN 模式下应暴露给模型的工具定义列表
        运行逻辑：按排序后的工具名遍历，只保留在 config.plan_mode_tools 白名单内、
                 且在 tool_registry 中确实存在的工具，转换为 LLM 工具定义
        出参：list[LLMToolDefinition] - PLAN 模式可用的工具定义列表
        """
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
        """
        函数名：for_context
        入参：
          - context (LoopContext)：当前执行上下文，用于判断是否已执行过步骤
        功能：获取 BUILD 模式（常规执行模式）下，依据当前上下文状态应暴露给模型的
             工具定义列表
        运行逻辑：先通过 _allowed_tool_names 计算当前允许的工具名集合（受首轮探索门禁
                 影响），再按排序后的工具名遍历，只保留允许集合内、且确实存在的工具，
                 转换为 LLM 工具定义
        出参：list[LLMToolDefinition] - 当前上下文下可用的工具定义列表
        """

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
        """
        函数名：_allowed_tool_names
        入参：
          - context (LoopContext)：当前执行上下文
        功能：计算当前应允许暴露给模型的工具名集合，是首轮探索门禁的核心判断逻辑
        运行逻辑：
          1. 从全部已注册工具中排除 sub_agent_tools（如 SubAgent 场景下不允许递归 delegate）
          2. 若本轮已执行过步骤（context.steps 非空），或配置显式跳过探索门禁，
             直接返回全部可用工具（不做收窄）
          3. 否则（首轮且未跳过门禁）：取"可用工具"与"探索类工具白名单"的交集；
             若交集为空（异常兜底），退回返回全部可用工具，保证至少有工具可用
        出参：set[str] - 当前允许暴露的工具名集合
        """
        # 先排除 sub_agent_tools 中的工具（如 delegate 在 sub-agent 模式下）
        exclude = self.config.sub_agent_tools
        available = set(self.tool_registry.list_tools_excluding(exclude))
        # 已执行过步骤，或配置为跳过首轮探索门禁（子 agent 场景）：直接给全量工具
        if context.steps or self.config.skip_exploration_gate:
            return available
        exploration_tools = available.intersection(self.config.exploration_tools)
        return exploration_tools or available

    def _ordered_tool_names(self) -> list[str]:
        """
        函数名：_ordered_tool_names
        入参：无
        功能：获取按 config.tool_order 优先级排序后的全部工具名列表
        运行逻辑：先排除 sub_agent_tools，再把已知顺序（tool_order 中列出且存在）的
                 工具名排前面，剩余未在 tool_order 中声明的工具名按注册表原有顺序追加在后面
        出参：list[str] - 排序后的工具名列表
        """
        # 使用 list_tools_excluding 排除 sub_agent_tools
        names = self.tool_registry.list_tools_excluding(self.config.sub_agent_tools)
        known = [name for name in self.config.tool_order if name in names]
        unknown = [name for name in names if name not in self.config.tool_order]
        return known + unknown

    def get_plan_tool(self) -> PlanTool | None:
        """
        函数名：get_plan_tool
        入参：无
        功能：从工具注册表中获取 plan 工具实例（若已注册）
        运行逻辑：按名称 "plan" 查询注册表，并校验其类型确实是 PlanTool（延迟导入
                 避免循环依赖），类型不匹配或未注册则返回 None
        出参：PlanTool | None - plan 工具实例，不存在时为 None
        """
        from app.tools.plan_tool import PlanTool

        tool = self.tool_registry.get("plan")
        return tool if isinstance(tool, PlanTool) else None
