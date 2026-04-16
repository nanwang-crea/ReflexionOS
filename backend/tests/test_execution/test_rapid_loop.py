import pytest
from unittest.mock import AsyncMock, MagicMock
from app.execution.rapid_loop import RapidExecutionLoop
from app.execution.context_manager import ExecutionContext
from app.llm.base import Message, LLMResponse
from app.models.action import Action, ToolCall
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
        """测试任务正常完成"""
        mock_llm.complete.return_value = LLMResponse(
            content='{"content": "任务完成", "tool_calls": []}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        result = await execution_loop.run("测试任务")
        
        assert result.status.value == "completed"
        assert "任务完成" in result.result
    
    @pytest.mark.asyncio
    async def test_execution_max_steps(self, execution_loop, mock_llm):
        """测试超过最大步数"""
        mock_llm.complete.return_value = LLMResponse(
            content='{"content": "继续执行", "tool_calls": [{"name": "mock", "args": {}}]}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        result = await execution_loop.run("无限循环任务")
        
        assert result.status.value == "completed"
    
    @pytest.mark.asyncio
    async def test_parse_action_with_tool_call(self, execution_loop):
        """测试解析工具调用"""
        content = '{"content": "读取文件", "tool_calls": [{"name": "mock", "args": {"path": "test.py"}}]}'
        
        action = execution_loop._parse_action(content)
        
        assert action.content == "读取文件"
        assert action.has_tool_calls
        assert action.tool_calls[0].name == "mock"
        assert action.tool_calls[0].args["path"] == "test.py"
    
    @pytest.mark.asyncio
    async def test_parse_action_with_message_only(self, execution_loop):
        """测试解析纯消息"""
        content = '{"content": "你好！有什么可以帮助你的吗？", "tool_calls": []}'
        
        action = execution_loop._parse_action(content)
        
        assert action.content == "你好！有什么可以帮助你的吗？"
        assert not action.has_tool_calls
        assert action.is_finish
    
    @pytest.mark.asyncio
    async def test_parse_action_pure_text(self, execution_loop):
        """测试解析纯文本（无法解析为JSON）"""
        content = "你好，我是 AI 助手"
        
        action = execution_loop._parse_action(content)
        
        assert action.content == "你好，我是 AI 助手"
        assert not action.has_tool_calls
