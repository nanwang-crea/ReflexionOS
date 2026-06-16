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

    最终消息顺序：system prompt → context sections → Tier 3 compacted summary(system)
                   → Tier 2 截断消息(system) → Tier 1 recent context messages(user/assistant/tool)
                   → Task Anchor(user)
    """

    def __init__(
        self,
        prompt_manager: PromptManager,
        max_context_groups: int,
        tool_output_max_chars: int = 2_400,
        task_anchor_interval: int = 0,
    ):
        self.prompt_manager = prompt_manager
        self.max_context_groups = max_context_groups
        self.tool_output_max_chars = tool_output_max_chars
        self.task_anchor_interval = task_anchor_interval

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
                project_root=context.project_path,
                coding_mode=context.agent_mode != "plan",
            )
        messages = [LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)]

        self._inject_context_sections(context, messages)

        # Tier 3: LLM 压缩摘要（如有），包含 [session_recall can retrieve] 标记
        if context.compacted_summary:
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[Compacted historical context]\n{context.compacted_summary}",
                )
            )

        if context.compacted_summary and context.group_count > 1:
            last_continue_group = context.metadata.get("_last_compaction_continue_group", 0)
            if last_continue_group != context.group_count:
                messages.append(
                    LLMMessage(
                        role=MessageRole.USER,
                        content=f"Continue the task using tools. Original task: {context.task}",
                    )
                )
                context.metadata["_last_compaction_continue_group"] = context.group_count

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

        # Plan state injection: 每轮注入当前计划状态，确保 LLM 始终知道当前步骤
        if context.plan and context.plan.current_step:
            plan_status = self._build_plan_status(context.plan)
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=plan_status))

        # Task Anchor: 首轮注入，之后按 task_anchor_interval 周期性注入
        # FINAL_SUMMARY 阶段由 build_final_summary 单独处理。
        should_inject_anchor = False
        if context.group_count <= 1:
            should_inject_anchor = True
        elif self.task_anchor_interval > 0 and context.group_count % self.task_anchor_interval == 0:
            last_injected_group = context.metadata.get("_last_anchor_group", 0)
            if last_injected_group != context.group_count:
                should_inject_anchor = True
                context.metadata["_last_anchor_group"] = context.group_count

        if should_inject_anchor:
            messages.append(LLMMessage(role=MessageRole.USER, content=f"[Task Reminder] {context.task}"))

        prefill = context.metadata.get("_prefill_assistant")
        if prefill:
            messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=prefill))

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

        messages.append(LLMMessage(role=MessageRole.USER, content=context.task_content))

        return messages

    def build_final_summary(self, context: LoopContext) -> list[LLMMessage]:
        """构建不暴露工具列表的最终总结消息。"""
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=(
                    "You are a pragmatic workspace agent. Write the final answer directly "
                    "from the provided context. Do not call tools."
                ),
            )
        ]

        self._inject_context_sections(context, messages)

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
        messages.append(LLMMessage(role=MessageRole.USER, content=context.task_content))

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

    @staticmethod
    def _build_plan_status(plan) -> str:
        """构建轻量级计划状态注入，每轮调用，~50 tokens"""
        current = plan.current_step
        total = len(plan.steps)
        completed = sum(1 for s in plan.steps if s.status == "completed")
        step_num = next(
            (i + 1 for i, s in enumerate(plan.steps) if s.status == "in_progress"),
            0,
        )
        return (
            f"[Plan ► Step {step_num}/{total}: {current.content}] "
            f"({completed}/{total} completed) → "
            f"work on this step, then call plan to mark it completed."
        )

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
