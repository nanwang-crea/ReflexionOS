import os
import sys

from app.execution.context_manager import LoopContext
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMMessage, LLMToolCall, MessageRole
from app.memory.text_compaction import truncate_head_tail


class LoopMessageBuilder:
    """
    三级上下文模型的消息构建器：
    - Tier 1: 完整保真 —— 最近 N 组消息，原文不改
    - Tier 2: 截断但可见 —— 超出窗口的旧消息逐条截断，每条仍在 context 中
    - Tier 3: LLM 摘要 —— 极端压力时旧消息压缩为摘要，细节可 session_recall 回溯

    最终消息顺序：system prompt → context sections → plan → Tier 3 compacted summary(system)
                   → Tier 2 截断消息(system) → Tier 1 recent context messages(user/assistant/tool)
                   → Task Anchor(user)
    """

    def __init__(
        self,
        prompt_manager: PromptManager,
        max_context_groups: int,
        tool_output_max_chars: int = 2_400,
    ):
        self.prompt_manager = prompt_manager
        self.max_context_groups = max_context_groups
        # Tier 2 中 tool output 的最大字符数，超出部分 head+tail 截断
        self.tool_output_max_chars = tool_output_max_chars

    @staticmethod
    def _inject_context_sections(context: LoopContext, messages: list[LLMMessage]) -> None:
        """注入三层上下文中的静态层：system sections + supplemental context"""
        for section in context.system_sections or []:
            if str(section or "").strip():
                messages.append(LLMMessage(role=MessageRole.SYSTEM, content=str(section)))
        supplemental = context.supplemental_context
        if supplemental and str(supplemental).strip():
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=str(supplemental).strip()))

    def build(self, context: LoopContext) -> list[LLMMessage]:
        """构建完整的三级上下文消息列表，供 LLM 调用使用"""
        if context.agent_mode == "plan":
            system_prompt = self.prompt_manager.get_plan_mode_prompt(
                working_directory=context.project_path or os.getcwd(),
                platform=sys.platform,
                is_git_repo=os.path.isdir(
                    os.path.join(context.project_path or os.getcwd(), ".git")
                ),
            )
        else:
            system_prompt = self.prompt_manager.get_system_prompt(
                working_directory=context.project_path or os.getcwd(),
                platform=sys.platform,
                is_git_repo=os.path.isdir(
                    os.path.join(context.project_path or os.getcwd(), ".git")
                ),
            )
        messages = [LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)]

        self._inject_context_sections(context, messages)

        if context.plan:
            plan_parts = [context.plan.render_for_context()]
            current_step = context.plan.current_step
            if context.metadata.get("plan_update_required"):
                stagnant = context.metadata.get("steps_since_last_plan_update", 0)
                if stagnant >= 15:
                    plan_parts.append(
                        "🔴 CRITICAL: 当前步骤已执行 15+ 轮工具调用但未更新计划状态。"
                        "必须立即调用 plan.step_done 或 plan.block。"
                        "忽略计划更新会导致执行效率严重下降。"
                    )
                elif stagnant >= 10:
                    plan_parts.append(
                        "🚨 Plan WARNING: 当前步骤已执行 10+ 轮工具调用但未更新计划状态。"
                        "请立即评估当前步骤是否已完成，如果是，调用 plan.step_done。"
                    )
                elif stagnant >= 5:
                    plan_parts.append(
                        "⚠️ Plan reminder: 当前步骤已执行 5 轮工具调用但未更新计划状态。"
                        "一个步骤可以需要多次工具调用，但如果步骤已完成，请调用 plan.step_done。"
                    )
                else:
                    plan_parts.append(
                        "Plan update reminder: a single plan step may require multiple tool calls. "
                        "Continue using tools while the current step is still in progress. "
                        "When the current step is complete, blocked, or needs replanning, "
                        "call plan.step_done, plan.block, or plan.adjust."
                    )
            completed_findings = context.plan.completed_findings()
            if completed_findings:
                findings_text = "\n".join(f"- {f}" for f in completed_findings)
                plan_parts.append(f"Findings from completed steps:\n{findings_text}")
            messages.append(
                LLMMessage(role=MessageRole.SYSTEM, content="\n\n".join(plan_parts))
            )

        # Tier 3: LLM 压缩摘要（如有），包含 [session_recall can retrieve] 标记
        if context.compacted_summary:
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[Compacted historical context]\n{context.compacted_summary}",
                )
            )

        # Tier 2: 超出窗口的旧消息，逐条截断但始终可见
        tier2_messages = self._build_tier2_messages(context)
        for msg in tier2_messages:
            messages.append(msg)

        # Tier 1: 最近 N 组消息，完整保真
        for msg in self.recent_context_messages(context):
            tool_calls = [LLMToolCall(**tool_call) for tool_call in msg.get("tool_calls", [])]
            messages.append(
                LLMMessage(
                    role=msg["role"],
                    content=msg.get("content"),
                    tool_calls=tool_calls,
                    tool_call_id=msg.get("tool_call_id"),
                )
            )

        # Task Anchor: 仅在首轮（尚未执行工具）时注入原始任务，
        # 避免中间执行轮次重复注入导致模型陷入循环。
        # FINAL_SUMMARY 阶段由 build_final_summary 单独处理。
        if context.group_count <= 1:
            messages.append(LLMMessage(role=MessageRole.USER, content=context.task))

        # Plan Focus: 当计划存在且当前步骤切换时注入一次焦点提示，
        # 后续轮次不重复注入，避免循环。用 _injected_focus_step_id 追踪。
        if context.plan and context.plan.current_step is not None:
            current_step_id = context.plan.current_step.id
            injected_id = context.metadata.get("_injected_focus_step_id")
            if injected_id != current_step_id:
                completed = sum(1 for s in context.plan.steps if s.status == "completed")
                total = len(context.plan.steps)
                focus_text = (
                    f"[Plan Focus] Now executing step {current_step_id}/{total} "
                    f"({completed} completed): {context.plan.current_step.description}\n"
                    f"Goal: {context.plan.goal}\n"
                    "When done, call plan.step_done with findings. "
                    "If blocked, call plan.block with the reason."
                )
                messages.append(LLMMessage(role=MessageRole.USER, content=focus_text))
                context.metadata["_injected_focus_step_id"] = current_step_id

        return messages

    def build_initial_plan(self, context: LoopContext) -> list[LLMMessage]:
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM, content=self.prompt_manager.get_initial_plan_prompt()
            )
        ]

        self._inject_context_sections(context, messages)

        for msg in self.recent_context_messages(context):
            if msg["role"] not in {MessageRole.USER, MessageRole.ASSISTANT}:
                continue
            if not msg.get("content"):
                continue
            messages.append(LLMMessage(role=msg["role"], content=msg.get("content")))

        messages.append(LLMMessage(role=MessageRole.USER, content=context.task))

        return messages

    def build_final_summary(self, context: LoopContext) -> list[LLMMessage]:
        """构建不暴露工具列表的最终总结消息。"""
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=(
                    "You are an autonomous coding agent. Write the final answer directly "
                    "from the provided context. Do not call tools."
                ),
            )
        ]

        self._inject_context_sections(context, messages)

        if context.plan:
            messages.append(
                LLMMessage(role=MessageRole.SYSTEM, content=context.plan.render_for_context())
            )
            completed_findings = context.plan.completed_findings()
            if completed_findings:
                findings_text = "\n".join(f"- {f}" for f in completed_findings)
                messages.append(
                    LLMMessage(
                        role=MessageRole.SYSTEM,
                        content=f"Findings from completed steps:\n{findings_text}",
                    )
                )

        if context.compacted_summary:
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[Compacted historical context]\n{context.compacted_summary}",
                )
            )

        for msg in self._build_tier2_messages(context):
            messages.append(msg)

        for msg in self.recent_context_messages(context):
            content = msg.get("content")
            if msg["role"] == MessageRole.TOOL:
                if isinstance(content, str) and content.strip():
                    messages.append(
                        LLMMessage(role=MessageRole.TOOL, content=content, tool_call_id=msg.get("tool_call_id"))
                    )
                continue

            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                tool_calls = [LLMToolCall(**tc) for tc in msg["tool_calls"]]
                messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls))
                continue

            messages.append(LLMMessage(role=msg["role"], content=content))

        # Task Anchor: 在最终总结时重新注入原始任务，确保回答围绕用户需求
        messages.append(LLMMessage(role=MessageRole.USER, content=context.task))

        return messages

    def _build_tier2_messages(self, context: LoopContext) -> list[LLMMessage]:
        """
        构建 Tier 2 消息：超出窗口的旧消息逐条截断但始终可见。
        tool output 超过 tool_output_max_chars 时 head+tail 截断并标记 [session_recall can retrieve]。
        保持原始消息角色，确保 tool_call_id / tool_calls 关联不被破坏。
        """
        grouped = self._group_messages(context.messages)
        if len(grouped) <= self.max_context_groups:
            return []

        older_groups = grouped[: -self.max_context_groups]
        tier2: list[LLMMessage] = []

        for group in older_groups:
            for msg in group:
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                        tool_calls_list = msg.get("tool_calls")
                        kwargs: dict = {"role": MessageRole.ASSISTANT, "content": content}
                        if tool_calls_list:
                            kwargs["tool_calls"] = [LLMToolCall(**tc) for tc in tool_calls_list]
                        tier2.append(LLMMessage(**kwargs))
                    continue

                if msg["role"] == MessageRole.TOOL:
                    if content == "[Old tool result content cleared]":
                        tier2.append(
                            LLMMessage(role=MessageRole.TOOL, content=content, tool_call_id=msg.get("tool_call_id"))
                        )
                        continue
                    if len(content) > self.tool_output_max_chars:
                        content = truncate_head_tail(
                            content,
                            self.tool_output_max_chars,
                            head_chars=1_600,
                            tail_chars=600,
                            reason="session_recall retrieve",
                        )
                    tier2.append(
                        LLMMessage(role=MessageRole.TOOL, content=content, tool_call_id=msg.get("tool_call_id"))
                    )
                elif msg["role"] == MessageRole.ASSISTANT:
                    tool_calls_list = msg.get("tool_calls")
                    kwargs: dict = {"role": MessageRole.ASSISTANT, "content": content}
                    if tool_calls_list:
                        kwargs["tool_calls"] = [LLMToolCall(**tc) for tc in tool_calls_list]
                    tier2.append(LLMMessage(**kwargs))
                elif msg["role"] == MessageRole.USER:
                    # 仅在 anchor 会注入时（group_count <= 1）过滤重复 task
                    if content == context.task and context.group_count <= 1:
                        continue
                    tier2.append(LLMMessage(role=MessageRole.USER, content=content))

        return tier2

    def recent_context_messages(self, context: LoopContext) -> list[dict]:
        """获取 Tier 1 最近 N 组消息。当 Task Anchor 会注入时（group_count <= 1），跳过重复的 task user 消息。"""
        if not context.messages:
            return []

        grouped_messages: list[list[dict]] = []
        active_tool_group: list[dict] | None = None

        for msg in context.messages:
            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                active_tool_group = [msg]
                grouped_messages.append(active_tool_group)
                continue

            if msg["role"] == MessageRole.TOOL and active_tool_group is not None:
                active_tool_group.append(msg)
                continue

            active_tool_group = None
            grouped_messages.append([msg])

        recent_groups = grouped_messages[-self.max_context_groups :]
        flat = [message for group in recent_groups for message in group]
        # 仅在 anchor 会注入时过滤重复，避免中间轮次丢失用户消息
        should_dedup_task = context.group_count <= 1
        return [
            m for m in flat
            if not (should_dedup_task and m["role"] == MessageRole.USER and m.get("content") == context.task)
        ]

    def _group_messages(self, messages: list[dict]) -> list[list[dict]]:
        """将消息按 assistant+tool_calls 开组的方式分组，确保 tool_call 与 tool output 不被拆分"""
        return self._group_messages_static(messages)

    @staticmethod
    def _group_messages_static(messages: list[dict]) -> list[list[dict]]:
        """将消息按 assistant+tool_calls 开组的方式分组，确保 tool_call 与 tool output 不被拆分"""
        grouped: list[list[dict]] = []
        active_tool_group: list[dict] | None = None
        for msg in messages:
            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                active_tool_group = [msg]
                grouped.append(active_tool_group)
                continue
            if msg["role"] == MessageRole.TOOL and active_tool_group is not None:
                active_tool_group.append(msg)
                continue
            active_tool_group = None
            grouped.append([msg])
        return grouped
