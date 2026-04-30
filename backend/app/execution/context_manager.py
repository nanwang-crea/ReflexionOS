import logging
from datetime import datetime
from typing import Any

from app.llm.base import MessageRole
from app.execution.models import LoopStep
from app.execution.plan_engine import Plan

logger = logging.getLogger(__name__)


class LoopContext:
    """Agent loop 上下文"""

    def __init__(self, task: str, project_path: str | None = None, run_id: str | None = None):
        self.task = task
        self.project_path = project_path
        self.run_id = run_id or f"run-{id(self)}"
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

    @classmethod
    def from_run_input(
        cls,
        *,
        task: str,
        project_path: str | None = None,
        run_id: str | None = None,
        seed_messages: list[dict[str, str]] | None = None,
        supplemental_context: str | None = None,
        system_sections: list[str] | None = None,
    ) -> "LoopContext":
        context = cls(task=task, project_path=project_path, run_id=run_id)

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
        self.history.append({
            "action": action,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
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
        tool_call_id: str | None = None
    ) -> None:
        """添加消息"""
        message: dict[str, Any] = {
            "role": role,
            "timestamp": datetime.now().isoformat()
        }

        if content is not None:
            message["content"] = content
        if tool_calls:
            message["tool_calls"] = tool_calls
        if tool_call_id:
            message["tool_call_id"] = tool_call_id

        self.messages.append(message)
