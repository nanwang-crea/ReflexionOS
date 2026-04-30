from app.execution.context_manager import LoopContext
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMMessage, LLMToolCall, LLMToolDefinition


class LoopMessageBuilder:
    """Build model messages from loop context and phase-specific tool definitions."""

    def __init__(self, prompt_manager: PromptManager, max_context_groups: int):
        self.prompt_manager = prompt_manager
        self.max_context_groups = max_context_groups

    def build(self, context: LoopContext, tools: list[LLMToolDefinition]) -> list[LLMMessage]:
        messages = [
            LLMMessage(role="system", content=self.prompt_manager.get_system_prompt(tools))
        ]

        for section in getattr(context, "system_sections", []) or []:
            if str(section or "").strip():
                messages.append(LLMMessage(role="system", content=str(section)))

        supplemental = getattr(context, "supplemental_context", None)
        if supplemental and str(supplemental).strip():
            messages.append(LLMMessage(role="system", content=str(supplemental).strip()))

        if context.plan:
            messages.append(LLMMessage(role="system", content=context.plan.render_for_context()))
            completed_findings = context.plan.completed_findings()
            if completed_findings:
                findings_text = "\n".join(f"- {f}" for f in completed_findings)
                messages.append(LLMMessage(role="system", content=f"前序步骤发现:\n{findings_text}"))

        for msg in self.recent_context_messages(context):
            tool_calls = [
                LLMToolCall(**tool_call)
                for tool_call in msg.get("tool_calls", [])
            ]
            messages.append(LLMMessage(
                role=msg["role"],
                content=msg.get("content"),
                tool_calls=tool_calls,
                tool_call_id=msg.get("tool_call_id"),
            ))

        return messages

    def build_initial_plan(self, context: LoopContext) -> list[LLMMessage]:
        messages = [
            LLMMessage(role="system", content=self.prompt_manager.get_initial_plan_prompt())
        ]

        for section in getattr(context, "system_sections", []) or []:
            if str(section or "").strip():
                messages.append(LLMMessage(role="system", content=str(section)))

        supplemental = getattr(context, "supplemental_context", None)
        if supplemental and str(supplemental).strip():
            messages.append(LLMMessage(role="system", content=str(supplemental).strip()))

        for msg in self.recent_context_messages(context):
            if msg["role"] not in {"user", "assistant"}:
                continue
            if not msg.get("content"):
                continue
            messages.append(LLMMessage(role=msg["role"], content=msg.get("content")))

        return messages

    def recent_context_messages(self, context: LoopContext) -> list[dict]:
        if not context.messages:
            return []

        grouped_messages: list[list[dict]] = []
        active_tool_group: list[dict] | None = None

        for msg in context.messages:
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                active_tool_group = [msg]
                grouped_messages.append(active_tool_group)
                continue

            if msg["role"] == "tool" and active_tool_group is not None:
                active_tool_group.append(msg)
                continue

            active_tool_group = None
            grouped_messages.append([msg])

        recent_groups = grouped_messages[-self.max_context_groups:]
        return [
            message
            for group in recent_groups
            for message in group
        ]
