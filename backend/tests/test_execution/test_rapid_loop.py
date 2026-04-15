import pytest
from unittest.mock import AsyncMock, MagicMock
from app.execution.rapid_loop import RapidExecutionLoop
from app.execution.context_manager import ExecutionContext
from app.llm.base import Message, LLMResponse
from app.models.action import Action, ActionType
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
        # Mock LLM返回finish
        mock_llm.complete.return_value = LLMResponse(
            content='{"type": "finish", "thought": "完成", "confidence": 0.95}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        result = await execution_loop.run("测试任务")
        
        assert result.status.value == "completed"
        assert "0.95" in result.result
    
    @pytest.mark.asyncio
    async def test_execution_max_steps(self, execution_loop, mock_llm):
        """测试超过最大步数"""
        # Mock LLM始终返回工具调用
        mock_llm.complete.return_value = LLMResponse(
            content='{"type": "tool_call", "thought": "继续", "tool": "mock", "args": {}, "confidence": 0.8}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        result = await execution_loop.run("无限循环任务")
        
        assert result.status.value == "failed"
        assert "最大步数" in result.result
    
    @pytest.mark.asyncio
    async def test_decide_action_with_tool_call(self, execution_loop, mock_llm):
        """测试LLM决策返回工具调用"""
        context = ExecutionContext(task="测试任务")
        
        mock_llm.complete.return_value = LLMResponse(
            content='{"type": "tool_call", "thought": "读取文件", "tool": "mock", "args": {"path": "test.py"}, "confidence": 0.8}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        action = await execution_loop.decide_action(context)
        
        assert action.type == ActionType.TOOL_CALL
        assert action.tool == "mock"
        assert action.args["path"] == "test.py"
    
    @pytest.mark.asyncio
    async def test_decide_action_with_finish(self, execution_loop, mock_llm):
        """测试LLM决策返回完成"""
        context = ExecutionContext(task="测试任务")
        
        mock_llm.complete.return_value = LLMResponse(
            content='{"type": "finish", "thought": "完成", "confidence": 0.95}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        action = await execution_loop.decide_action(context)
        
        assert action.type == ActionType.FINISH
        assert action.confidence == 0.95
