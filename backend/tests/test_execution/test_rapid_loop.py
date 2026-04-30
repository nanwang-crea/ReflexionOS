import asyncio
from unittest.mock import AsyncMock

import pytest

from app.execution.models import LoopResult, LoopStatus, StepStatus
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm.base import LLMToolCall, StreamChunk
from app.llm.retry import RetryExhaustedError
from app.tools.base import BaseTool, ToolApprovalRequest, ToolResult
from app.tools.plan_tool import PlanTool
from app.tools.registry import ToolRegistry


class MockTool(BaseTool):
    """测试用Mock工具"""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def description(self) -> str:
        return "Mock tool for testing"

    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path"}},
            },
        }

    async def execute(self, args):
        return ToolResult(success=True, output="mock output")


class ApprovalTool(BaseTool):
    @property
    def name(self) -> str:
        return "approval_tool"

    @property
    def description(self) -> str:
        return "Tool that requires approval"

    async def execute(self, args):
        return ToolResult(
            success=False,
            approval_required=True,
            approval=ToolApprovalRequest(
                approval_id="approval-1",
                tool_name="approval_tool",
                summary="需要审批",
                payload={"value": 1},
            ),
        )


class TestRapidExecutionLoop:
    @staticmethod
    async def _stream_response(content="", tool_calls=None, finish_reason="stop"):
        if content:
            yield StreamChunk(type="content", content=content)

        if tool_calls:
            yield StreamChunk(type="tool_calls", tool_calls=tool_calls, finish_reason=finish_reason)
        else:
            yield StreamChunk(type="done", finish_reason=finish_reason)

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.get_model_name = lambda: "gpt-4"
        return llm

    @pytest.fixture
    def tool_registry(self):
        registry = ToolRegistry()
        registry.register(MockTool())
        return registry

    @pytest.fixture
    def execution_loop(self, mock_llm, tool_registry):
        return RapidExecutionLoop(llm=mock_llm, tool_registry=tool_registry, max_steps=5)

    @pytest.mark.asyncio
    async def test_execution_with_finish(self, execution_loop, mock_llm):
        """测试任务正常完成（无工具调用）"""

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content="任务完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("测试任务")

        assert isinstance(result, LoopResult)
        assert result.status == LoopStatus.COMPLETED
        assert "任务完成" in result.result
        assert not hasattr(result, "project_id")
        assert not hasattr(result, "session_id")
        assert not hasattr(result, "project_path")
        assert not hasattr(result, "provider_id")
        assert not hasattr(result, "model_id")

    @pytest.mark.asyncio
    async def test_execution_fails_when_model_returns_no_content_and_no_tool_calls(
        self,
        execution_loop,
        mock_llm,
    ):
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content=""):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("测试空响应")

        assert result.status == LoopStatus.FAILED
        assert result.result == "执行异常: 模型未返回任何内容，也未发起工具调用"

    @pytest.mark.asyncio
    async def test_execution_with_tool_call(self, execution_loop, mock_llm):
        """测试带工具调用的执行"""
        # 第一次调用返回工具调用，第二次返回完成
        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="执行工具",
                    tool_calls=[LLMToolCall(name="mock", arguments={})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="完成"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("执行工具任务")

        assert len(result.steps) == 1
        assert result.steps[0].tool == "mock"
        assert result.steps[0].status.value == "success"
        assert result.result == "完成"

    @pytest.mark.asyncio
    async def test_tool_results_are_sent_back_to_llm(self, execution_loop, mock_llm):
        """测试工具调用和结果会进入下一轮 LLM 消息"""
        captured_calls = []
        tool_call = LLMToolCall(name="mock", arguments={"path": "README.md"})

        async def mock_stream(messages, tools=None):
            captured_calls.append((messages, tools))
            call_index = len(captured_calls)

            if call_index == 1:
                async for chunk in self._stream_response(
                    content="先读取 README", tool_calls=[tool_call], finish_reason="tool_calls"
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="README 已读取完成"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("帮我看一下当前 README")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "README 已读取完成"
        assert len(captured_calls) == 2

        second_messages, second_tools = captured_calls[1]
        assert second_tools is not None

        assistant_message = next(
            msg for msg in second_messages if msg.role == "assistant" and msg.tool_calls
        )
        assert assistant_message.content == "先读取 README"
        assert assistant_message.tool_calls[0].name == "mock"
        assert assistant_message.tool_calls[0].arguments == {"path": "README.md"}

        tool_message = next(msg for msg in second_messages if msg.role == "tool")
        assert tool_message.content == "mock output"
        assert tool_message.tool_call_id == tool_call.id

    @pytest.mark.asyncio
    async def test_final_response_fallback_when_no_content_after_tools(
        self,
        execution_loop,
        mock_llm,
    ):
        """测试工具执行后没有直接答案时，走兜底最终回答"""
        captured_calls = []

        async def mock_stream(messages, tools=None):
            captured_calls.append((messages, tools))
            call_index = len(captured_calls)

            if call_index == 1:
                async for chunk in self._stream_response(
                    content="先查看项目结构",
                    tool_calls=[LLMToolCall(name="mock", arguments={})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            elif call_index == 2:
                async for chunk in self._stream_response(content=""):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="项目采用前后端分离结构。"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("其项目结构是怎么样的呢？")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "项目采用前后端分离结构。"
        assert len(captured_calls) == 3

        summary_messages, summary_tools = captured_calls[2]
        assert summary_tools is None
        assert summary_messages[-1].role == "user"
        assert "Write the final answer for the user now." in summary_messages[-1].content

    @pytest.mark.asyncio
    async def test_rapid_loop_includes_seeded_history_before_current_user_message(
        self,
        execution_loop,
        mock_llm,
    ):
        captured = {}

        async def mock_stream(messages, tools=None):
            captured["messages"] = messages
            async for chunk in self._stream_response(content="ok"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run(
            "继续处理",
            seed_messages=[
                {"role": "user", "content": "上一轮需求"},
                {"role": "assistant", "content": "上一轮结论"},
            ],
            supplemental_context="当前目标: 修 memory",
        )

        contents = [message.content for message in captured["messages"] if message.content]
        assert contents.index("上一轮需求") < contents.index("继续处理")
        assert any("当前目标: 修 memory" in content for content in contents)

    @pytest.mark.asyncio
    async def test_execution_max_steps(self, execution_loop, mock_llm):
        """测试超过最大步数"""

        # 始终返回工具调用
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                content="继续执行",
                tool_calls=[LLMToolCall(name="mock", arguments={})],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("无限循环任务")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 5

    @pytest.mark.asyncio
    async def test_event_callback_emits_tool_start_and_result(self, mock_llm, tool_registry):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=tool_registry, max_steps=2, event_callback=callback
        )
        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="先检查文件",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "."})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="检查完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("检查项目")

        event_types = [event["type"] for event in events]
        assert "tool:start" in event_types
        assert "tool:result" in event_types
        assert "run:complete" in event_types

    @pytest.mark.asyncio
    async def test_tool_approval_required_pauses_run_without_error_recovery(self, mock_llm):
        registry = ToolRegistry()
        registry.register(ApprovalTool())
        events = []
        captured_calls = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=3,
            event_callback=callback,
        )

        tool_call = LLMToolCall(name="approval_tool", arguments={"value": 1})

        async def mock_stream(messages, tools=None):
            captured_calls.append(messages)
            async for chunk in self._stream_response(
                content="需要先审批",
                tool_calls=[tool_call],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("执行需要审批的工具")

        assert result.status == LoopStatus.WAITING_FOR_APPROVAL
        waiting_step = result.steps[-1]
        assert waiting_step.status == StepStatus.WAITING_FOR_APPROVAL
        assert waiting_step.tool_call_id == tool_call.id
        assert waiting_step.approval_id == "approval-1"

        event_types = [event["type"] for event in events]
        assert "approval:required" in event_types
        assert "tool:error" not in event_types
        assert "run:complete" not in event_types
        assert len(captured_calls) == 1

        tool_start_event = next(event for event in events if event["type"] == "tool:start")
        assert tool_start_event["data"]["tool_call_id"] == tool_call.id

        approval_event = next(event for event in events if event["type"] == "approval:required")
        assert approval_event["data"]["tool_call_id"] == tool_call.id
        assert approval_event["data"]["approval_id"] == "approval-1"

    @pytest.mark.asyncio
    async def test_initial_plan_preflight_emits_plan_without_streaming_preface(self, mock_llm):
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())
        events = []
        captured_tools = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=2,
            event_callback=callback,
        )

        async def mock_stream(messages, tools=None):
            captured_tools.append(tools)
            if len(captured_tools) == 1:
                async for chunk in self._stream_response(
                    content="我先制定计划。",
                    tool_calls=[
                        LLMToolCall(
                            name="plan",
                            arguments={
                                "action": "create",
                                "goal": "修复计划显示",
                                "steps": ["定位问题", "修改实现", "验证结果"],
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="开始执行。"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("请修复计划窗口流式显示和位置")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "开始执行。"
        event_types = [event["type"] for event in events]
        assert event_types.index("plan:updated") < event_types.index("llm:content")
        assert not any(
            event["type"] == "llm:content" and event["data"].get("content") == "我先制定计划。"
            for event in events
        )
        plan_event = next(event for event in events if event["type"] == "plan:updated")
        assert plan_event["data"]["goal"] == "修复计划显示"
        assert [step["description"] for step in plan_event["data"]["steps"]] == [
            "定位问题",
            "修改实现",
            "验证结果",
        ]
        main_tool_names = [tool.name for tool in captured_tools[1]]
        assert "plan" in main_tool_names
        main_plan_tool = next(tool for tool in captured_tools[1] if tool.name == "plan")
        assert "create" not in str(main_plan_tool.parameters)

    @pytest.mark.asyncio
    async def test_initial_plan_preflight_can_decline_and_keep_normal_streaming(self, mock_llm):
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())
        events = []
        captured_tools = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=2,
            event_callback=callback,
        )

        async def mock_stream(messages, tools=None):
            captured_tools.append(tools)
            if len(captured_tools) == 1:
                async for chunk in self._stream_response(content="NO_PLAN"):
                    yield chunk
                return

            async for chunk in self._stream_response(content="直接回答。"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("解释一下这个函数")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "直接回答。"
        assert not any(event["type"] == "plan:updated" for event in events)
        assert any(
            event["type"] == "llm:content" and event["data"].get("content") == "直接回答。"
            for event in events
        )
        assert [tool.name for tool in captured_tools[1]] == ["mock"]

    @pytest.mark.asyncio
    async def test_event_callback(self, mock_llm, tool_registry):
        """测试事件回调"""
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=tool_registry, max_steps=5, event_callback=callback
        )

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content="任务完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("测试任务")

        # 检查事件
        execution_start = next(e for e in events if e["type"] == "run:start")
        assert execution_start["data"]["run_id"].startswith("run-")
        assert "execution_id" not in execution_start["data"]
        assert any(e["type"] == "llm:content" for e in events)
        assert any(e["type"] == "run:complete" for e in events)
        assert not any(e["type"] == "llm:start" for e in events)

    @pytest.mark.asyncio
    async def test_does_not_emit_legacy_llm_thought_or_tool_call_events(
        self, mock_llm, tool_registry
    ):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=tool_registry, max_steps=2, event_callback=callback
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="我先查看项目结构，再继续探索。",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "."})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="项目结构已经确认。"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("介绍一下当前项目结构")

        event_types = [event["type"] for event in events]
        assert "llm:thought" not in event_types
        assert "llm:tool_call" not in event_types
        assert "summary:start" not in event_types
        assert "summary:complete" not in event_types

    @pytest.mark.asyncio
    async def test_execution_returns_cancelled_when_task_is_cancelled(
        self,
        mock_llm,
        tool_registry,
    ):
        """测试取消运行中的执行会返回 cancelled 状态并发送事件"""
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=tool_registry, max_steps=2, event_callback=callback
        )

        async def mock_stream(messages, tools=None):
            yield StreamChunk(type="content", content="正在分析项目结构")
            await asyncio.sleep(5)
            yield StreamChunk(type="done", finish_reason="stop")

        mock_llm.stream_complete = mock_stream

        task = asyncio.create_task(execution_loop.run("请检查项目结构", run_id="run-cancel-test"))
        await asyncio.sleep(0)
        task.cancel()

        result = await task

        assert result.id == "run-cancel-test"
        assert result.status == LoopStatus.CANCELLED
        assert result.result == "执行已取消"
        assert any(event["type"] == "run:cancelled" for event in events)

    @pytest.mark.asyncio
    async def test_retry_exhaustion_cancels_execution_without_error_recovery(
        self, mock_llm, tool_registry
    ):
        events = []
        call_count = 0

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=tool_registry, max_steps=3, event_callback=callback
        )

        async def mock_stream(messages, tools=None):
            nonlocal call_count
            call_count += 1
            raise RetryExhaustedError(ValueError("network down"), max_retries=5)
            yield

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("需要联网的任务")

        assert call_count == 1
        assert result.status == LoopStatus.CANCELLED
        assert result.result == "执行已取消：LLM 重试次数已达上限"
        event_types = [event["type"] for event in events]
        assert "run:cancelled" in event_types
        assert "run:error" not in event_types

    @pytest.mark.asyncio
    async def test_failed_execution_emits_execution_error_event(self, mock_llm, tool_registry):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=tool_registry, max_steps=3, event_callback=callback
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="先执行工具",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "README.md"})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            raise RuntimeError("boom")
            yield

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("失败任务")

        assert result.status == LoopStatus.FAILED
        assert any(event["type"] == "run:error" for event in events)

    @pytest.mark.asyncio
    async def test_tool_failure_recovery(self, execution_loop, mock_llm):
        """测试工具失败恢复"""

        # 注册一个会失败的工具
        class FailTool(BaseTool):
            @property
            def name(self) -> str:
                return "fail"

            @property
            def description(self) -> str:
                return "Fail tool"

            async def execute(self, args):
                return ToolResult(success=False, error="Failed")

        execution_loop.tool_registry.register(FailTool())

        # 第一次调用返回失败工具
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                tool_calls=[LLMToolCall(name="fail", arguments={})], finish_reason="tool_calls"
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("测试失败任务")

        assert result.steps[0].status.value == "failed"
