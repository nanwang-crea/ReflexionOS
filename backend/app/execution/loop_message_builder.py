from app.execution.context_manager import LoopContext
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMMessage, LLMToolCall, LLMToolDefinition, MessageRole
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

    def build(self, context: LoopContext, tools: list[LLMToolDefinition]) -> list[LLMMessage]:
        """构建完整的三级上下文消息列表，供 LLM 调用使用"""
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=section)
            for section in self.prompt_manager.get_system_prompt_sections(tools)
        ]

        self._inject_context_sections(context, messages)

        if context.plan:
            messages.append(
                LLMMessage(role=MessageRole.SYSTEM, content=context.plan.render_for_context())
            )
            current_step = context.plan.current_step
            if current_step is not None:
                messages.append(
                    LLMMessage(
                        role=MessageRole.SYSTEM,
                        content=(
                            f"Current plan step: {current_step.description}\n"
                            "Only do work that directly advances this step."
                        ),
                    )
                )
            if context.metadata.get("plan_update_required"):
                messages.append(
                    LLMMessage(
                        role=MessageRole.SYSTEM,
                        content=(
                            "Plan update reminder: a single plan step may require multiple tool calls. "
                            "Continue using tools while the current step is still in progress. "
                            "When the current step is complete, blocked, or needs replanning, "
                            "call plan.step_done, plan.block, or plan.adjust."
                        ),
                    )
                )
            completed_findings = context.plan.completed_findings()
            if completed_findings:
                findings_text = "\n".join(f"- {f}" for f in completed_findings)
                messages.append(
                    LLMMessage(role=MessageRole.SYSTEM, content=f"Findings from completed steps:\n{findings_text}")
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

        # Task Anchor: 原始用户输入作为不可截断的最新 user 消息始终放在最后
        messages.append(LLMMessage(role=MessageRole.USER, content=context.task))

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
                        LLMMessage(role=MessageRole.SYSTEM, content=f"[tool output] {content}")
                    )
                continue

            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                tool_names = [tc.get("name", "") for tc in msg["tool_calls"]]
                prefix = f"[assistant called: {', '.join(tool_names)}]"
                text = f"{prefix} {content}" if content else prefix
                messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=text))
                continue

            messages.append(LLMMessage(role=msg["role"], content=content))

        return messages

    def _build_tier2_messages(self, context: LoopContext) -> list[LLMMessage]:
        """
        构建 Tier 2 消息：超出窗口的旧消息逐条截断但始终可见。
        tool output 超过 tool_output_max_chars 时 head+tail 截断并标记 [session_recall can retrieve]，
        assistant/user 消息保留原文（user 消息中与 task 重复的跳过，避免与 Task Anchor 重复）。
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
                    continue
                if msg["role"] == MessageRole.TOOL and len(content) > self.tool_output_max_chars:
                    truncated = truncate_head_tail(
                        content,
                        self.tool_output_max_chars,
                        head_chars=1_600,
                        tail_chars=600,
                        reason="session_recall retrieve",
                    )
                    tier2.append(
                        LLMMessage(role=MessageRole.SYSTEM, content=f"[tool output] {truncated}")
                    )
                elif msg["role"] == MessageRole.TOOL:
                    tier2.append(
                        LLMMessage(role=MessageRole.SYSTEM, content=f"[tool output] {content}")
                    )
                elif msg["role"] == MessageRole.ASSISTANT:
                    text = content
                    if msg.get("tool_calls"):
                        tool_names = [tc.get("name", "") for tc in msg["tool_calls"]]
                        text = f"[assistant called: {', '.join(tool_names)}] {text}"
                    tier2.append(LLMMessage(role=MessageRole.SYSTEM, content=text))
                elif msg["role"] == MessageRole.USER:
                    if content == context.task:
                        continue
                    tier2.append(LLMMessage(role=MessageRole.SYSTEM, content=f"[user] {content}"))

        return tier2

    def recent_context_messages(self, context: LoopContext) -> list[dict]:
        """获取 Tier 1 最近 N 组消息，并跳过与 Task Anchor 重复的 user 消息"""
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
        return [
            m for m in flat
            if not (m["role"] == MessageRole.USER and m.get("content") == context.task)
        ]

    def _group_messages(self, messages: list[dict]) -> list[list[dict]]:
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
