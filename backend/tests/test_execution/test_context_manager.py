from app.execution.context_manager import LoopContext
from app.models.action import ToolCall


class TestLoopContext:
    
    def test_create_context(self):
        context = LoopContext(task="测试任务")
        
        assert context.task == "测试任务"
        assert context.run_id is not None
        assert len(context.history) == 0
    
    def test_update_history(self):
        context = LoopContext(task="测试任务")
        tool_call = ToolCall(name="file", args={"path": "test.py"})
        
        context.update_history(tool_call, "执行结果")
        
        assert len(context.history) == 1
        assert context.history[0]["result"] == "执行结果"
    
    def test_get_recent_history(self):
        context = LoopContext(task="测试任务")
        
        for i in range(5):
            tool_call = ToolCall(name="file", args={"index": i})
            context.update_history(tool_call, f"结果{i}")
        
        recent = context.get_recent_history(3)
        
        assert len(recent) == 3
    
    def test_add_step(self):
        from app.execution.models import LoopStep, StepStatus
        
        context = LoopContext(task="测试任务")
        step = LoopStep(
            step_number=1,
            tool="file",
            args={"path": "test.py"},
            status=StepStatus.RUNNING
        )
        
        context.add_step(step)
        
        assert len(context.steps) == 1
        assert context.current_step_number == 1
    
    def test_add_message(self):
        context = LoopContext(task="测试任务")
        
        context.add_message("user", "你好")
        context.add_message("assistant", "你好，有什么可以帮助你的？")
        
        assert len(context.messages) == 2
        assert context.get_last_message() == "你好，有什么可以帮助你的？"
    
    def test_get_workspace_context(self):
        context = LoopContext(task="测试任务")
        
        workspace_context = context.get_workspace_context()
        
        assert "测试任务" in workspace_context

    def test_to_dict_uses_run_id(self):
        context = LoopContext(task="测试任务", run_id="run-123")

        payload = context.to_dict()

        assert payload["run_id"] == "run-123"
        assert "execution_id" not in payload

    def test_from_run_input_filters_seed_messages_and_adds_current_task(self):
        context = LoopContext.from_run_input(
            task="继续处理",
            project_path="/tmp/reflexion",
            run_id="run-123",
            seed_messages=[
                {"role": "user", "content": "上一轮需求"},
                {"role": "assistant", "content": "  上一轮结论  "},
                {"role": "system", "content": "should be ignored"},
                {"role": "tool", "content": ""},
                {"role": "tool", "content": "tool output"},
                "bad seed",
            ],
            supplemental_context="当前目标: 修 memory",
            system_sections=["AGENTS instructions"],
        )

        assert context.task == "继续处理"
        assert context.project_path == "/tmp/reflexion"
        assert context.run_id == "run-123"
        assert context.supplemental_context == "当前目标: 修 memory"
        assert context.system_sections == ["AGENTS instructions"]
        assert [
            (message["role"], message.get("content"))
            for message in context.messages
        ] == [
            ("user", "上一轮需求"),
            ("assistant", "上一轮结论"),
            ("tool", "tool output"),
            ("user", "继续处理"),
        ]
