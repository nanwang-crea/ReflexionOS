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

    def __init__(self, task: str, project_path: str | None = None, run_id: str | None = None, agent_mode: str = "build"):
        self.task = task
        self.project_path = project_path
        self.run_id = run_id or f"run-{id(self)}"
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
        agent_mode: str = "build",
        seed_messages: list[dict[str, str]] | None = None,
        supplemental_context: str | None = None,
        system_sections: list[str] | None = None,
    ) -> "LoopContext":
        context = cls(task=task, project_path=project_path, run_id=run_id, agent_mode=agent_mode)

        allowed_seed_roles = {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL}
        for seeded in seed_messages or []:
            if not isinstance(seeded, dict):
                continue
            role = str(seeded.get("role") or "").strip().lower()
            if role not in allowed_seed_roles:
                continue
            content = seeded.get("content")
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue
            context.add_message(role, content)

        context.supplemental_context = supplemental_context
        context.system_sections = system_sections or []
        context.add_message("user", task)
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
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """添加消息"""
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
