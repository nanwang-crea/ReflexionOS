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
    def _inject_context_sections(
        context: LoopContext, messages: list[LLMMessage]
    ) -> None:
        """注入三层上下文中的静态层：system sections"""
        for section in context.system_sections or []:
            if str(section or "").strip():
                messages.append(
                    LLMMessage(role=MessageRole.SYSTEM, content=str(section))
                )

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

    def build_initial_plan(self, context: LoopContext) -> list[LLMMessage]:
        messages = [
            LLMMessage(
                role=MessageRole.SYSTEM,
                content=self.prompt_manager.get_initial_plan_prompt(),
            )
        ]

        # 注意：计划阶段不注入 system_sections（AGENTS.md、skills、MEMORY等），
        # 这些上下文对判断"是否需要计划"是噪声，反而让 LLM 倾向于创建不必要的计划。
        # 主循环 build() 中会注入完整上下文。

        # 从 recent_messages 中提取用户/助手消息
        # 注意：from_run_input 已保证 recent_messages 中包含当前任务的用户消息，
        # 无需再追加 task_content，否则会导致重复
        recent = context.compressor.get_recent_messages()
        last_user_idx = None
        for i, msg in enumerate(recent):
            if msg["role"] not in {MessageRole.USER, MessageRole.ASSISTANT}:
                continue
            if not msg.get("content"):
                continue
            messages.append(LLMMessage(role=msg["role"], content=msg.get("content")))
            if msg["role"] == MessageRole.USER:
                last_user_idx = len(messages) - 1

        task_content = context.task_content

        # 如果 recent_messages 中没有用户消息（如单元测试或非标准入口），
        # 回退到直接使用 task_content
        if last_user_idx is None and task_content:
            if isinstance(task_content, list):
                valid = [p for p in task_content if isinstance(p, dict) and p.get("type")]
                task_content = valid if valid else ""
            if task_content:
                messages.append(LLMMessage(role=MessageRole.USER, content=task_content))
                last_user_idx = len(messages) - 1
        elif isinstance(task_content, list) and last_user_idx is not None:
            # 如果 task_content 是多模态（含图片等），替换最后一条用户消息
            # 因为 recent_messages 中可能只有纯文本版本
            valid = [p for p in task_content if isinstance(p, dict) and p.get("type")]
            if valid:
                messages[last_user_idx] = LLMMessage(role=MessageRole.USER, content=valid)

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
