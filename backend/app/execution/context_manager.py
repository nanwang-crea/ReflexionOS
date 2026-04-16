from typing import List, Dict, Any, Optional
from app.models.execution import ExecutionStep, StepStatus
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ExecutionContext:
    """Agent 执行上下文"""
    
    def __init__(self, task: str, project_path: Optional[str] = None, execution_id: str = None):
        self.task = task
        self.project_path = project_path
        self.execution_id = execution_id or f"exec-{id(self)}"
        self.history: List[Dict[str, Any]] = []
        self.steps: List[ExecutionStep] = []
        self.messages: List[Dict[str, str]] = []
        self.current_step_number = 0
        self.workspace_snapshot: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
    
    def update_history(self, action: Any, result: str) -> None:
        """更新执行历史"""
        self.history.append({
            "action": action,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"更新执行历史")
    
    def add_step(self, step: ExecutionStep) -> None:
        """添加执行步骤"""
        self.steps.append(step)
        self.current_step_number = step.step_number
        logger.info(f"添加执行步骤 {step.step_number}: {step.tool}")
    
    def add_message(self, role: str, content: str) -> None:
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_last_message(self) -> Optional[str]:
        """获取最后一条消息"""
        if self.messages:
            return self.messages[-1].get("content")
        return None
    
    def update_step(self, step_id: str, status: StepStatus, output: Optional[str] = None) -> None:
        """更新步骤状态"""
        for step in self.steps:
            if step.id == step_id:
                step.status = status
                if output:
                    step.output = output
                logger.info(f"更新步骤 {step_id} 状态为 {status}")
                break
    
    def get_recent_history(self, limit: int = 3) -> List[Dict[str, Any]]:
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
    
    def to_dict(self) -> Dict[str, Any]:
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
