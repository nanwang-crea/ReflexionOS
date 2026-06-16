from types import SimpleNamespace

from app.execution.context_manager import LoopContext


class TestLoopContext:
    def test_create_context(self):
        context = LoopContext(task="test task")

        assert context.task == "test task"
        assert context.run_id is not None
        assert len(context.history) == 0

    def test_update_history(self):
        context = LoopContext(task="test task")
        tool_call = SimpleNamespace(name="file", args={"path": "test.py"})

        context.update_history(tool_call, "done")

        assert len(context.history) == 1
        assert context.history[0]["result"] == "done"

    def test_add_step(self):
        from app.execution.models import LoopStep, StepStatus

        context = LoopContext(task="test task")
        step = LoopStep(
            step_number=1, tool="file", args={"path": "test.py"}, status=StepStatus.RUNNING
        )

        context.add_step(step)

        assert len(context.steps) == 1
        assert context.current_step_number == 1

    def test_add_message(self):
        context = LoopContext(task="test task")

        context.add_message("user", "hello")
        context.add_message("assistant", "hi there")

        assert len(context.messages) == 2
        assert context.messages[-1]["content"] == "hi there"

    def test_from_run_input_filters_seed_messages_and_adds_current_task(self):
        context = LoopContext.from_run_input(
            task="continue work",
            project_path="/tmp/reflexion",
            run_id="run-123",
            seed_messages=[
                {"role": "user", "content": "previous request"},
                {"role": "assistant", "content": " previous answer "},
                {"role": "system", "content": "should be ignored"},
                {"role": "tool", "content": ""},
                {"role": "tool", "content": "tool output", "tool_call_id": "call_001"},
                "bad seed",
            ],
            supplemental_context="Current goal: repair image input",
            system_sections=["AGENTS instructions"],
        )

        assert context.task == "continue work"
        assert context.project_path == "/tmp/reflexion"
        assert context.run_id == "run-123"
        assert context.supplemental_context == "Current goal: repair image input"
        assert context.system_sections == ["AGENTS instructions"]
        assert [(message["role"], message.get("content")) for message in context.messages] == [
            ("user", "previous request"),
            ("assistant", "previous answer"),
            ("tool", "tool output"),
            ("user", "continue work"),
        ]

    def test_from_run_input_supports_tool_calls_in_seed_messages(self):
        context = LoopContext.from_run_input(
            task="continue",
            seed_messages=[
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_001", "name": "file", "arguments": {"action": "read", "path": "a.py"}},
                ]},
                {"role": "tool", "content": "file content here", "tool_call_id": "call_001"},
                {"role": "assistant", "content": "read complete"},
            ],
        )

        msgs = context.messages
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["tool_calls"][0]["name"] == "file"
        assert msgs[0].get("content") is None

        assert msgs[1]["role"] == "tool"
        assert msgs[1]["content"] == "file content here"
        assert msgs[1]["tool_call_id"] == "call_001"

        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"] == "read complete"

        assert msgs[3]["role"] == "user"
        assert msgs[3]["content"] == "continue"

    def test_from_run_input_supports_multimodal_current_turn_message(self):
        image_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "Please inspect this image"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
            ],
        }

        context = LoopContext.from_run_input(
            task="Please inspect this image",
            seed_messages=[{"role": "assistant", "content": "previous summary"}],
            current_turn_message=image_message,
        )

        assert context.messages[-1]["role"] == "user"
        assert context.messages[-1]["content"] == image_message["content"]
        assert not any(
            message["role"] == "user" and message.get("content") == "Please inspect this image"
            for message in context.messages
        )

    def test_from_run_input_skips_tool_message_without_tool_call_id(self):
        context = LoopContext.from_run_input(
            task="continue",
            seed_messages=[
                {"role": "tool", "content": "orphan tool result"},
            ],
        )

        assert len(context.messages) == 1
        assert context.messages[0]["role"] == "user"

    def test_from_run_input_deduplicates_task_with_last_user_seed(self):
        context = LoopContext.from_run_input(
            task="continue",
            seed_messages=[
                {"role": "assistant", "content": "still analyzing..."},
                {"role": "user", "content": "continue"},
            ],
        )

        user_msgs = [m for m in context.messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "continue"

    def test_from_run_input_appends_task_when_last_user_seed_differs(self):
        context = LoopContext.from_run_input(
            task="new task",
            seed_messages=[
                {"role": "user", "content": "old task"},
                {"role": "assistant", "content": "done"},
            ],
        )

        user_msgs = [m for m in context.messages if m["role"] == "user"]
        assert len(user_msgs) == 2
        assert user_msgs[0]["content"] == "old task"
        assert user_msgs[1]["content"] == "new task"
