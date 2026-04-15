import pytest
from app.execution.context_manager import ExecutionContext
from app.models.action import Action, ActionType


class TestExecutionContext:
    
    def test_create_context(self):
        context = ExecutionContext(task="测试任务")
        
        assert context.task == "测试任务"
        assert len(context.history) == 0
    
    def test_update_history(self):
        context = ExecutionContext(task="测试任务")
        action = Action(type=ActionType.TOOL_CALL, tool="file", args={"path": "test.py"})
        
        context.update_history(action, "执行结果")
        
        assert len(context.history) == 1
        assert context.history[0]["action"] == action
        assert context.history[0]["result"] == "执行结果"
    
    def test_get_recent_history(self):
        context = ExecutionContext(task="测试任务")
        
        for i in range(5):
            action = Action(type=ActionType.TOOL_CALL, tool="file", args={"index": i})
            context.update_history(action, f"结果{i}")
        
        recent = context.get_recent_history(3)
        
        assert len(recent) == 3
        assert recent[0]["result"] == "结果2"
        assert recent[2]["result"] == "结果4"
    
    def test_add_step(self):
        from app.models.execution import ExecutionStep, StepStatus
        
        context = ExecutionContext(task="测试任务")
        step = ExecutionStep(
            step_number=1,
            tool="file",
            args={"path": "test.py"},
            status=StepStatus.RUNNING
        )
        
        context.add_step(step)
        
        assert len(context.steps) == 1
        assert context.current_step_number == 1
    
    def test_get_workspace_context(self):
        context = ExecutionContext(task="测试任务")
        
        workspace_context = context.get_workspace_context()
        
        assert "测试任务" in workspace_context
