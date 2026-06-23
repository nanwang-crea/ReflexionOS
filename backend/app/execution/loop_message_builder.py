import os
import sys

from app.execution.context_manager import LoopContext
from app.execution.prompt_manager import PromptManager
from app.llm.base import LLMMessage, LLMToolCall, MessageRole


class LoopMessageBuilder:
    """
    三级上下文模型的消息构建器：
    - Tier 1: 完整保真 —— 最近 N 组消息，原文不改
    - Tier 2: 截断但可见 —— 超出窗口的旧消息逐条截断，每条仍在 context 中
    - Tier 3: LLM 摘要 —— 极端压力时旧消息压缩为摘要，细节可 session_recall 回溯

    最终消息顺序：system prompt（含 Skills 等静态上下文） → Tier 3 compacted summary(system)
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

    def build(self, context: LoopContext) -> list[LLMMessage]:
        """构建完整的三级上下文消息列表，供 LLM 调用使用

        注意：system_sections（AGENTS.md、Skills 等）已合并到 PromptManager.get_system_prompt() 中，
        不再在此处单独注入。
        """
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

        # 双层记忆注入：SessionTracker（跟踪）+ WorkingMemory（语义）
        # SessionTracker 在前，高注意力权重；WM 在后，提供决策/变量
        memory_messages = self._build_memory_injection(context)
        messages.extend(memory_messages)

        # Tier 3: LLM 压缩摘要（如有），包含 [session_recall can retrieve] 标记
        if context.compressor.get_compacted_summary():
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[Compacted historical context — session_recall can retrieve full details]\n{context.compressor.get_compacted_summary()}",
                )
            )

        if (
            context.compressor.get_compacted_summary()
            and context.compressor.get_group_count() > 1
        ):
            last_continue_group = context.metadata.get(
                "_last_compaction_continue_group", 0
            )
            if last_continue_group != context.compressor.get_group_count():
                messages.append(
                    LLMMessage(
                        role=MessageRole.USER,
                        content=f"Continue the task using tools. Original task: {context.task}",
                    )
                )
                context.metadata["_last_compaction_continue_group"] = (
                    context.compressor.get_group_count()
                )

        # Tier 2: 超出窗口的旧消息，逐条截断但始终可见
        tier2_messages = context.compressor.build_tier2_messages()
        for msg in tier2_messages:
            messages.append(msg)

        # Tier 1: 最近 N 组消息，完整保真
        for msg in context.compressor.get_recent_messages():
            tool_calls = [
                LLMToolCall(**tool_call) for tool_call in msg.get("tool_calls", [])
            ]
            messages.append(
                LLMMessage(
                    role=msg["role"],
                    content=msg.get("content"),
                    tool_calls=tool_calls,
                    tool_call_id=msg.get("tool_call_id"),
                )
            )

        # Recovered plan injection: 如果有旧计划但当前未激活，注入提示让 LLM 自己决定
        if hasattr(context, 'recovered_plan') and context.recovered_plan and not context.plan:
            messages.append(LLMMessage(
                role=MessageRole.SYSTEM,
                content=f"<system-reminder>之前存在计划：\n{context.recovered_plan.goal}\n\n"
                f"步骤概览：\n" + "\n".join(
                    f"  {i+1}. [{s.status}] {s.content}"
                    for i, s in enumerate(context.recovered_plan.steps)
                ) +
                "\n\n你可以决定继续执行这个计划（使用 plan tool），或创建新计划，或直接开始工作。</system-reminder>"
            ))

        # Plan state injection: 每轮注入当前计划状态，确保 LLM 始终知道当前步骤
        if context.plan and context.plan.current_step:
            plan_status = self._build_plan_status(context.plan)
            messages.append(LLMMessage(role=MessageRole.SYSTEM, content=plan_status))

        # Task Anchor: 首轮注入，之后按 task_anchor_interval 周期性注入
        # FINAL_SUMMARY 阶段由 build_final_summary 单独处理。
        # 注意：首轮不需要注入 Task Anchor，因为用户的初始消息（含图片）已经在 context.messages 中
        should_inject_anchor = False
        if context.compressor.get_group_count() > 1:  # 只在非首轮时考虑注入
            if (
                self.task_anchor_interval > 0
                and context.compressor.get_group_count() % self.task_anchor_interval
                == 0
            ):
                last_injected_group = context.metadata.get("_last_anchor_group", 0)
                if last_injected_group != context.compressor.get_group_count():
                    should_inject_anchor = True
                    context.metadata["_last_anchor_group"] = (
                        context.compressor.get_group_count()
                    )

        if should_inject_anchor:
            # 周期性提醒任务，使用纯文本即可
            messages.append(
                LLMMessage(
                    role=MessageRole.USER, content=f"[Task Reminder] {context.task}"
                )
            )

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

        # 双层记忆注入：SessionTracker + WorkingMemory
        memory_messages = self._build_memory_injection(context)
        messages.extend(memory_messages)

        if context.compressor.get_compacted_summary():
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[Compacted historical context — session_recall can retrieve full details]\n{context.compressor.get_compacted_summary()}",
                )
            )

        for msg in context.compressor.build_tier2_messages():
            messages.append(msg)

        for msg in context.compressor.get_recent_messages():
            content = msg.get("content")
            if msg["role"] == MessageRole.TOOL:
                if isinstance(content, str) and content.strip():
                    messages.append(
                        LLMMessage(
                            role=MessageRole.TOOL,
                            content=content,
                            tool_call_id=msg.get("tool_call_id"),
                        )
                    )
                continue

            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                tool_calls = [LLMToolCall(**tc) for tc in msg["tool_calls"]]
                messages.append(
                    LLMMessage(
                        role=MessageRole.ASSISTANT,
                        content=content,
                        tool_calls=tool_calls,
                    )
                )
                continue

            messages.append(LLMMessage(role=msg["role"], content=content))

        # Task Anchor: 在最终总结时重新注入原始任务，确保回答围绕用户需求（支持多模态内容）
        task_content = context.task_content
        if isinstance(task_content, list):
            valid = [p for p in task_content if isinstance(p, dict) and p.get("type")]
            task_content = valid if valid else ""
        messages.append(LLMMessage(role=MessageRole.USER, content=task_content))

        return messages

    def _build_memory_injection(self, context: LoopContext) -> list[LLMMessage]:
        """构建双层记忆注入：SessionTracker（跟踪）+ WorkingMemory（语义）

        返回的 messages 按顺序插入到 system prompt 之后。
        SessionTracker 在前，提供极简的文件/工具跟踪列表（高注意力）。
        WorkingMemory 在后，提供决策、变量、错误等语义内容。
        """
        messages: list[LLMMessage] = []

        # 第一层：SessionTracker — 极简跟踪，始终可见
        tracker_section = context.session_tracker.to_prompt_section()
        if tracker_section:
            # 追加行为指令，告诉模型不要重复读取已知文件
            instruction = (
                "\n\nIMPORTANT: Files listed above have been read this session. "
                "DO NOT re-read them unless you need specific line ranges not "
                "captured in Working Memory below. Use session_recall to retrieve "
                "full content of previously read files."
            )
            messages.append(
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content=tracker_section + instruction,
                )
            )

        # 第二层：Working Memory — 语义化内容
        if not context.working_memory.is_empty():
            wm_section = context.working_memory.to_prompt_section()
            if wm_section:
                messages.append(
                    LLMMessage(
                        role=MessageRole.SYSTEM,
                        content=wm_section,
                    )
                )

        return messages

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
