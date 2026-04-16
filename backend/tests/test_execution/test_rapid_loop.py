import pytest
from unittest.mock import AsyncMock
from app.execution.rapid_loop import RapidExecutionLoop, ExecutionState
from app.execution.context_manager import ExecutionContext
from app.llm.base import LLMMessage, LLMResponse, LLMToolCall
from app.tools.registry import ToolRegistry
from app.tools.base import BaseTool, ToolResult


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
    
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.get_model_name.return_value = "gpt-4"
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
        mock_llm.complete.return_value = LLMResponse(
            content='任务完成',
            tool_calls=[],
            finish_reason='stop'
        )
        
        result = await execution_loop.run("测试任务")
        
        assert result.status.value == "completed"
        assert "任务完成" in result.result
    
    @pytest.mark.asyncio
    async def test_execution_with_tool_call(self, execution_loop, mock_llm):
        """测试带工具调用的执行"""
        from app.llm.base import StreamChunk
        
        # 第一次调用返回工具调用，第二次返回完成
        call_count = [0]
        
        async def mock_complete(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMResponse(
                    content='执行工具',
                    tool_calls=[LLMToolCall(name="mock", arguments={})],
                    finish_reason='tool_calls'
                )
            else:
                return LLMResponse(
                    content='任务完成',
                    tool_calls=[],
                    finish_reason='stop'
                )
        
        mock_llm.complete = mock_complete
        
        # 模拟 stream_complete 用于总结
        async def mock_stream(messages, tools=None):
            yield StreamChunk(type="content", content="完成")
            yield StreamChunk(type="done")
        
        mock_llm.stream_complete = mock_stream
        
        result = await execution_loop.run("执行工具任务")
        
        assert len(result.steps) == 1
        assert result.steps[0].tool == "mock"
        assert result.steps[0].status.value == "success"
    
    @pytest.mark.asyncio
    async def test_execution_max_steps(self, execution_loop, mock_llm):
        """测试超过最大步数"""
        # 始终返回工具调用
        mock_llm.complete.return_value = LLMResponse(
            content='继续执行',
            tool_calls=[LLMToolCall(name="mock", arguments={})],
            finish_reason='tool_calls'
        )
        
        result = await execution_loop.run("无限循环任务")
        
        assert result.status.value == "completed"
        assert len(result.steps) == 5
    
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
        
        mock_llm.complete.return_value = LLMResponse(
            content='任务完成',
            tool_calls=[],
            finish_reason='stop'
        )
        
        await execution_loop.run("测试任务")
        
        # 检查事件
        assert any(e["type"] == "execution:start" for e in events)
        assert any(e["type"] == "execution:complete" for e in events)
    
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
        mock_llm.complete.return_value = LLMResponse(
            content='',
            tool_calls=[LLMToolCall(name="fail", arguments={})],
            finish_reason='tool_calls'
        )
        
        result = await execution_loop.run("测试失败任务")
        
        assert result.steps[0].status.value == "failed"
