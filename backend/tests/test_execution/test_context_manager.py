from app.execution.context_manager import ExecutionContext
from app.models.action import ToolCall


class TestExecutionContext:
    
    def test_create_context(self):
        context = ExecutionContext(task="测试任务")
        
        assert context.task == "测试任务"
        assert len(context.history) == 0
    
    def test_update_history(self):
        context = ExecutionContext(task="测试任务")
        tool_call = ToolCall(name="file", args={"path": "test.py"})
        
        context.update_history(tool_call, "执行结果")
        
        assert len(context.history) == 1
        assert context.history[0]["result"] == "执行结果"
    
    def test_get_recent_history(self):
        context = ExecutionContext(task="测试任务")
        
        for i in range(5):
            tool_call = ToolCall(name="file", args={"index": i})
            context.update_history(tool_call, f"结果{i}")
        
        recent = context.get_recent_history(3)
        
        assert len(recent) == 3
    
    def test_add_step(self):
        from app.execution.models import ExecutionStep, StepStatus
        
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
    
    def test_add_message(self):
        context = ExecutionContext(task="测试任务")
        
        context.add_message("user", "你好")
        context.add_message("assistant", "你好，有什么可以帮助你的？")
        
        assert len(context.messages) == 2
        assert context.get_last_message() == "你好，有什么可以帮助你的？"
    
    def test_get_workspace_context(self):
        context = ExecutionContext(task="测试任务")
        
        workspace_context = context.get_workspace_context()
        
        assert "测试任务" in workspace_context
