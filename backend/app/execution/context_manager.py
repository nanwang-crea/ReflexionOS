import logging
from datetime import datetime
from typing import Any

from app.execution.models import LoopStep
from app.execution.plan_engine import Plan
from app.llm.base import MessageRole
from app.llm.token_counter import count_messages_tokens

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
        self.messages: list[dict[str, Any]] = []
        self.current_step_number = 0
        self.workspace_snapshot: dict[str, Any] = {}
        # Three-layer context assembly (Task 6)
        self.system_sections: list[str] = []
        self.supplemental_context: str | None = None
        # Plan engine
        self.plan: Plan | None = None
        self.plan_file_path: str | None = None
        # 三级上下文模型：实时 token 计数，超阈值触发 Tier 2 截断 / Tier 3 LLM 摘要
        self.total_tokens: int = 0
        # Tier 3 压缩后的摘要缓存，滚动更新；摘要中包含 [可 session_recall 取回] 标记
        self.compacted_summary: str | None = None
        # 消息分组计数，assistant+tool_calls 开启一组，用于判断窗口溢出
        self.group_count: int = 0
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
            (m for m in reversed(context.messages) if m["role"] == MessageRole.USER),
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
            context.add_message("user", current_content)

        return context

    def update_history(self, action: Any, result: str) -> None:
        """更新执行历史"""
        self.history.append(
            {"action": action, "result": result, "timestamp": datetime.now().isoformat()}
        )
        logger.debug("更新执行历史")

    def add_step(self, step: LoopStep) -> None:
        """添加执行步骤"""
        self.steps.append(step)
        self.current_step_number = step.step_number
        logger.info("添加执行步骤 %s: %s", step.step_number, step.tool)

    def add_message(
        self,
        role: str,
        content: str | list[dict] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """添加消息（支持多模态内容）

        Args:
            role: 消息角色
            content: 消息内容，支持：
                - str: 纯文本
                - list[dict]: 多模态内容（如 [{"type": "text", "text": "..."}, {"type": "image_url", "url": "..."}]）
            tool_calls: 工具调用列表
            tool_call_id: 工具调用 ID
        """
        message: dict[str, Any] = {"role": role, "timestamp": datetime.now().isoformat()}

        if content is not None:
            message["content"] = content
        if tool_calls:
            message["tool_calls"] = tool_calls
        if tool_call_id:
            message["tool_call_id"] = tool_call_id

        self.messages.append(message)
        # 累加 token 计数，用于实时上下文压力检测
        msg_tokens = count_messages_tokens([message])
        self.total_tokens += msg_tokens
        self._update_group_count(message)

    def recalculate_tokens(self) -> None:
        """Tier 3 压缩替换 messages 后，重新遍历计算 total_tokens"""
        self.total_tokens = count_messages_tokens(self.messages)

    def _update_group_count(self, message: dict[str, Any]) -> None:
        """更新消息分组计数：assistant+tool_calls 开启新组，tool 消息归入当前组"""
        if message["role"] == MessageRole.ASSISTANT and message.get("tool_calls"):
            self.group_count += 1
        elif message["role"] == MessageRole.TOOL:
            pass
        else:
            self.group_count += 1

    def prune_tool_outputs(
        self,
        protect_recent_groups: int = 2,
        minimum_recovery_tokens: int = 20_000,
        protected_tool_names: set[str] | None = None,
    ) -> int:
        """
        轻量裁剪：清除旧 tool output 的 content，回收 token。
        保护最近 protect_recent_groups 组消息，且至少回收 minimum_recovery_tokens 才执行。
        返回实际回收的 token 数。
        """
        from app.execution.loop_message_builder import LoopMessageBuilder

        if protected_tool_names is None:
            protected_tool_names = {"skill"}

        grouped = LoopMessageBuilder._group_messages_static(self.messages)
        if len(grouped) <= protect_recent_groups:
            return 0

        older_groups = grouped[:-protect_recent_groups]
        reclaimable = 0
        candidates: list[tuple[int, dict[str, Any]]] = []

        for group in older_groups:
            for msg in group:
                if msg["role"] != MessageRole.TOOL:
                    continue
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                if content == "[Old tool result content cleared]":
                    continue
                is_protected = any(
                    name in protected_tool_names
                    for tc in (group[0].get("tool_calls") or [])
                    for name in [tc.get("name", "")]
                )
                if is_protected:
                    continue
                msg_tokens = count_messages_tokens([msg])
                reclaimable += msg_tokens
                candidates.append((msg_tokens, msg))

        if reclaimable < minimum_recovery_tokens:
            return 0

        recovered = 0
        for msg_tokens, msg in candidates:
            msg["content"] = "[Old tool result content cleared]"
            recovered += msg_tokens

        self.recalculate_tokens()
        logger.info(
            "Pruned %d tool outputs, recovered ~%d tokens, remaining total_tokens=%d",
            len(candidates), recovered, self.total_tokens,
        )
        return recovered
