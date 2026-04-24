import logging
from datetime import datetime
from typing import Any

from app.execution.models import ExecutionStep, StepStatus

logger = logging.getLogger(__name__)


class ExecutionContext:
    """Agent 执行上下文"""
    
    def __init__(self, task: str, project_path: str | None = None, execution_id: str = None):
        self.task = task
        self.project_path = project_path
        self.execution_id = execution_id or f"exec-{id(self)}"
        self.history: list[dict[str, Any]] = []
        self.steps: list[ExecutionStep] = []
        self.messages: list[dict[str, Any]] = []
        self.current_step_number = 0
        self.workspace_snapshot: dict[str, Any] = {}
    
    def update_history(self, action: Any, result: str) -> None:
        """更新执行历史"""
        self.history.append({
            "action": action,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug("更新执行历史")
    
    def add_step(self, step: ExecutionStep) -> None:
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
    
    def get_last_message(self) -> str | None:
        """获取最后一条消息"""
        if self.messages:
            return self.messages[-1].get("content")
        return None
    
    def update_step(self, step_id: str, status: StepStatus, output: str | None = None) -> None:
        """更新步骤状态"""
        for step in self.steps:
            if step.id == step_id:
                step.status = status
                if output:
                    step.output = output
                logger.info("更新步骤 %s 状态为 %s", step_id, status)
                break
    
    def get_recent_history(self, limit: int = 3) -> list[dict[str, Any]]:
        """获取最近的执行历史"""
        return self.history[-limit:] if len(self.history) > limit else self.history
    
    def get_workspace_context(self) -> str:
        """获取工作区上下文信息"""
        context_parts = [f"任务: {self.task}"]
        
        if self.history:
            context_parts.append("\n最近的操作:")
            for i, item in enumerate(self.history[-3:], 1):
                action = item.get("action")
                if action:
                    if hasattr(action, 'name'):
                        context_parts.append(f"{i}. 工具调用: {action.name}")
                    elif hasattr(action, 'tool'):
                        context_parts.append(f"{i}. 工具调用: {action.tool}")
        
        return "\n".join(context_parts)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "task": self.task,
            "project_path": self.project_path,
            "execution_id": self.execution_id,
            "current_step": self.current_step_number,
            "total_steps": len(self.steps),
            "history_count": len(self.history),
            "messages": self.messages
        }
