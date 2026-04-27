import asyncio
from unittest.mock import AsyncMock

import pytest

from app.execution.context_manager import ExecutionContext
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm.base import LLMToolCall, StreamChunk
from app.tools.base import BaseTool, ToolResult
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
                "properties": {
                    "path": {"type": "string", "description": "File path"}
                }
            }
        }
    
    async def execute(self, args):
        return ToolResult(success=True, output="mock output")


class TestRapidExecutionLoop:

    @staticmethod
    async def _stream_response(content="", tool_calls=None, finish_reason="stop"):
        if content:
            yield StreamChunk(type="content", content=content)

        if tool_calls:
            yield StreamChunk(
                type="tool_calls",
                tool_calls=tool_calls,
                finish_reason=finish_reason
            )
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
        
        assert result.status.value == "completed"
        assert "任务完成" in result.result

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

        assert result.status.value == "failed"
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
                    finish_reason="tool_calls"
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
                    content="先读取 README",
                    tool_calls=[tool_call],
                    finish_reason="tool_calls"
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="README 已读取完成"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("帮我看一下当前 README")

        assert result.status.value == "completed"
        assert result.result == "README 已读取完成"
        assert len(captured_calls) == 2

        second_messages, second_tools = captured_calls[1]
        assert second_tools is not None

        assistant_message = next(
            msg for msg in second_messages
            if msg.role == "assistant" and msg.tool_calls
        )
        assert assistant_message.content == "先读取 README"
        assert assistant_message.tool_calls[0].name == "mock"
        assert assistant_message.tool_calls[0].arguments == {"path": "README.md"}

        tool_message = next(msg for msg in second_messages if msg.role == "tool")
        assert tool_message.content == "mock output"
        assert tool_message.tool_call_id == tool_call.id

    def test_build_messages_keeps_tool_outputs_with_matching_assistant_call(self, execution_loop):
        """测试历史截断时不会留下孤立的 tool 输出消息"""
        context = ExecutionContext(task="检查工具消息配对")
        first_call = LLMToolCall(id="call_alpha", name="mock", arguments={"path": "a.txt"})
        second_call = LLMToolCall(id="call_beta", name="mock", arguments={"path": "b.txt"})

        context.add_message(
            "assistant",
            content="先读取两个文件",
            tool_calls=[first_call.model_dump(), second_call.model_dump()]
        )
        context.add_message("tool", content="a output", tool_call_id=first_call.id)
        context.add_message("tool", content="b output", tool_call_id=second_call.id)

        for index in range(9):
            context.add_message("user", content=f"filler {index}")

        messages = execution_loop._build_messages(context)

        assistant_messages = [
            msg for msg in messages
            if msg.role == "assistant" and msg.tool_calls
        ]
        tool_messages = [msg for msg in messages if msg.role == "tool"]

        assert len(assistant_messages) == 1
        assert [tool_message.tool_call_id for tool_message in tool_messages] == [
            first_call.id,
            second_call.id,
        ]

    def test_build_messages_does_not_duplicate_initial_user_task(self, execution_loop):
        context = ExecutionContext(task="检查重复 user 消息")
        context.add_message("user", "检查重复 user 消息")

        messages = execution_loop._build_messages(context)
        user_contents = [message.content for message in messages if message.role == "user"]

        assert user_contents.count("检查重复 user 消息") == 1

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
                    finish_reason="tool_calls"
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

        assert result.status.value == "completed"
        assert result.result == "项目采用前后端分离结构。"
        assert len(captured_calls) == 3

        summary_messages, summary_tools = captured_calls[2]
        assert summary_tools is None
        assert summary_messages[-1].role == "user"
        assert "Write the final answer for the user now." in summary_messages[-1].content
    
    @pytest.mark.asyncio
    async def test_execution_max_steps(self, execution_loop, mock_llm):
        """测试超过最大步数"""
        # 始终返回工具调用
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                content="继续执行",
                tool_calls=[LLMToolCall(name="mock", arguments={})],
                finish_reason="tool_calls"
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream
        
        result = await execution_loop.run("无限循环任务")
        
        assert result.status.value == "completed"
        assert len(result.steps) == 5

    @pytest.mark.asyncio
    async def test_event_callback_emits_tool_start_and_result(self, mock_llm, tool_registry):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=2,
            event_callback=callback
        )
        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="先检查文件",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "."})],
                    finish_reason="tool_calls"
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
        assert "execution:complete" in event_types
    
    @pytest.mark.asyncio
    async def test_event_callback(self, mock_llm, tool_registry):
        """测试事件回调"""
        events = []
        
        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})
        
        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=5,
            event_callback=callback
        )
        
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content="任务完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream
        
        await execution_loop.run("测试任务")
        
        # 检查事件
        assert any(e["type"] == "execution:start" for e in events)
        assert any(e["type"] == "llm:content" for e in events)
        assert any(e["type"] == "execution:complete" for e in events)

    @pytest.mark.asyncio
    async def test_emits_llm_thought_before_tool_receipts(self, mock_llm, tool_registry):
        """测试带工具调用的 content 会作为中间思考事件发出"""
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=2,
            event_callback=callback
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="我先查看项目结构，再继续探索。",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "."})],
                    finish_reason="tool_calls"
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="项目结构已经确认。"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("介绍一下当前项目结构")

        thought_index = next(i for i, e in enumerate(events) if e["type"] == "llm:thought")
        tool_call_index = next(i for i, e in enumerate(events) if e["type"] == "llm:tool_call")

        assert events[thought_index]["data"]["content"] == "我先查看项目结构，再继续探索。"
        assert thought_index < tool_call_index

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
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=2,
            event_callback=callback
        )

        async def mock_stream(messages, tools=None):
            yield StreamChunk(type="content", content="正在分析项目结构")
            await asyncio.sleep(5)
            yield StreamChunk(type="done", finish_reason="stop")

        mock_llm.stream_complete = mock_stream

        task = asyncio.create_task(
            execution_loop.run("请检查项目结构", execution_id="exec-cancel-test")
        )
        await asyncio.sleep(0)
        task.cancel()

        result = await task

        assert result.id == "exec-cancel-test"
        assert result.status.value == "cancelled"
        assert result.result == "执行已取消"
        assert any(event["type"] == "execution:cancelled" for event in events)

    @pytest.mark.asyncio
    async def test_failed_execution_emits_execution_error_event(self, mock_llm, tool_registry):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=3,
            event_callback=callback
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="先执行工具",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "README.md"})],
                    finish_reason="tool_calls"
                ):
                    yield chunk
                return

            raise RuntimeError("boom")
            yield

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("失败任务")

        assert result.status.value == "failed"
        assert any(event["type"] == "execution:error" for event in events)

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
                tool_calls=[LLMToolCall(name="fail", arguments={})],
                finish_reason="tool_calls"
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream
        
        result = await execution_loop.run("测试失败任务")
        
        assert result.steps[0].status.value == "failed"
