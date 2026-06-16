import logging
from datetime import datetime
from typing import Any

from app.execution.context_compressor import ContextCompressor
from app.execution.models import LoopStep
from app.execution.plan_engine import Plan
from app.llm.base import MessageRole

logger = logging.getLogger(__name__)


class LoopContext:
    """Agent loop 上下文"""

    def __init__(
        self,
        task: str,
        project_path: str | None = None,
        run_id: str | None = None,
        agent_mode: str = "build",
        session_id: str | None = None,
        task_content: str | list[dict] | None = None,
    ):
        self.task = task  # 任务描述（纯文本），用于标识和日志
        self.task_content = task_content or task  # 实际传递给 LLM 的内容（支持多模态）
        self.project_path = project_path
        self.run_id = run_id or f"run-{id(self)}"
        self.session_id = session_id or self.run_id
        self.agent_mode = agent_mode
        self.history: list[dict[str, Any]] = []
        self.steps: list[LoopStep] = []
        self.current_step_number = 0
        self.workspace_snapshot: dict[str, Any] = {}
        # Three-layer context assembly (Task 6)
        self.system_sections: list[str] = []
        self.supplemental_context: str | None = None
        # Plan engine
        self.plan: Plan | None = None
        self.plan_file_path: str | None = None
        # Context compressor (三级上下文模型)
        from app.config.settings import config_manager

        self.compressor = ContextCompressor(
            max_context_groups=10,
            tool_output_max_chars=config_manager.settings.execution.tool_output_max_chars,
        )
        self.metadata: dict[str, Any] = {}

    @classmethod
    def from_run_input(
        cls,
        *,
        task: str,
        project_path: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        agent_mode: str = "build",
        history_messages: list[dict[str, Any]] | None = None,
        supplemental_context: str | None = None,
        system_sections: list[str] | None = None,
        task_content: str | list[dict] | None = None,
    ) -> "LoopContext":
        """
        从运行输入构造 LoopContext

        Args:
            task: 任务描述（纯文本）
            task_content: 实际传递给 LLM 的内容（支持多模态格式）
            history_messages: 历史对话消息，用于恢复上下文
            supplemental_context: 补充上下文（如项目文档）
            system_sections: 系统提示词片段列表
        """
        context = cls(
            task=task,
            project_path=project_path,
            run_id=run_id,
            agent_mode=agent_mode,
            session_id=session_id,
            task_content=task_content,
        )

        # 过滤并添加历史消息到 context.messages
        allowed_seed_roles = {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL}
        for seeded in history_messages or []:
            if not isinstance(seeded, dict):
                continue
            role = str(seeded.get("role") or "").strip().lower()
            if role not in allowed_seed_roles:
                continue

            tool_calls = seeded.get("tool_calls")
            tool_call_id = seeded.get("tool_call_id")

            if role == "tool" and not tool_call_id:
                logger.debug("Skipping tool seed message without tool_call_id")
                continue

            if role == "assistant" and tool_calls:
                content_str = None
                content = seeded.get("content")
                if isinstance(content, str) and content.strip():
                    content_str = content
                context.add_message(
                    role,
                    content=content_str,
                    tool_calls=tool_calls,
                )
                continue

            content = seeded.get("content")
            # 支持多模态内容（list）和纯文本（str）
            if isinstance(content, str):
                content = content.strip()
                if not content:
                    continue
            elif isinstance(content, list):
                # 多模态内容（文本 + 图片），保持原样
                pass
            else:
                continue

            context.add_message(role, content, tool_call_id=tool_call_id)

        context.supplemental_context = supplemental_context
        context.system_sections = system_sections or []

        # 确保最后一条消息是当前的用户任务（避免重复）
        # 支持多模态 task_content（带图片）或纯文本 task
        last_user_msg = next(
            (
                m
                for m in reversed(context.compressor.get_messages())
                if m["role"] == MessageRole.USER
            ),
            None,
        )

        # 使用 task_content（支持多模态）而不是 task（纯文本）
        current_content = task_content or task

        # 判断是否需要添加当前消息（避免重复）
        should_add = True
        if last_user_msg:
            last_content = last_user_msg.get("content")
            # 如果都是字符串，比较内容
            if isinstance(current_content, str) and isinstance(last_content, str):
                should_add = current_content != last_content
            # 如果都是列表（多模态），比较内容
            elif isinstance(current_content, list) and isinstance(last_content, list):
                should_add = current_content != last_content
            # 类型不同，认为是不同的消息
            else:
                should_add = True

        if should_add:
            context.add_message(MessageRole.USER, current_content)

        return context

    def update_history(self, action: Any, result: str) -> None:
        """更新执行历史"""
        self.history.append(
            {
                "action": action,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )
        logger.debug("更新执行历史")

    def add_step(self, step: LoopStep) -> None:
        """添加执行步骤"""
        self.steps.append(step)
        self.current_step_number = step.step_number
        logger.info("添加执行步骤 %s: %s", step.step_number, step.tool)

    def add_message(
        self,
        role: MessageRole,
        content: str | list[dict] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """添加消息（支持多模态内容）- 委托给 compressor"""
        self.compressor.add_message(role, content, tool_calls, tool_call_id)
