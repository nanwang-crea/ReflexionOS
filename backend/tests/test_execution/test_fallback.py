# 文件功能：测试 Agent 运行兜底机制 —— 主 run 超时后按备用模型链顺序尝试
# 文件描述：覆盖：备用链为空返回兜底文案、首个备用超时但第二个成功、备用链全部失败。
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.execution.models import LoopResult, LoopStatus
from app.execution.rapid_loop import RapidExecutionLoop
from app.models.llm_config import FallbackModelEntry
from app.services.agent_service import AgentService


def _make_result(result="模型结果", status=LoopStatus.COMPLETED):
    """构造一个 LoopResult 模拟备用 loop 的返回"""
    return LoopResult(
        id="run-fb",
        task="test",
        status=status,
        result=result,
        created_at=datetime.now(),
    )


def _entry(provider_id, model_id):
    return FallbackModelEntry(provider_id=provider_id, model_id=model_id)


class TestRunWithFallback:
    """_run_with_fallback 行为测试"""

    @pytest.fixture
    def service(self):
        with patch.object(AgentService, "__init__", lambda self, **kw: None):
            svc = AgentService.__new__(AgentService)
            svc.llm_provider_service = MagicMock()
            return svc

    @pytest.mark.asyncio
    async def test_empty_fallback_chain_returns_fallback_message(self, service):
        """备用链为空 → 返回兜底文案"""
        service.llm_provider_service.get_fallback_chain.return_value = []

        result = await service._run_with_fallback(
            task="test", task_content="test", project_path=None,
            run_id="run-1", session_id="sess-1", history_messages=None,
            agent_mode="build", original_loop=MagicMock(),
            run_tool_registry=MagicMock(), cancel_event=asyncio.Event(),
            on_llm_retry=None, event_callback=None, run_timeout=60,
        )

        assert result.status == LoopStatus.COMPLETED
        assert "当前无可用模型" in result.result

    @pytest.mark.asyncio
    async def test_first_fallback_succeeds_returns_its_result(self, service):
        """备用链第一个就成功 → 返回第一个的结果"""
        service.llm_provider_service.get_fallback_chain.return_value = [
            _entry("provider-a", "model-a"),
            _entry("provider-b", "model-b"),
        ]
        service.llm_provider_service.resolve_llm_config.return_value = MagicMock(
            context_window=128000,
        )

        expected = _make_result(result="备用 A 的答案")

        with patch("app.services.agent_service.LLMAdapterFactory.create", return_value=MagicMock()):
            async def quick_run(self, **kwargs):
                return expected

            with patch.object(RapidExecutionLoop, "run", quick_run):
                result = await service._run_with_fallback(
                    task="test", task_content="test", project_path=None,
                    run_id="run-1", session_id="sess-1", history_messages=None,
                    agent_mode="build", original_loop=MagicMock(_last_context=None),
                    run_tool_registry=MagicMock(), cancel_event=asyncio.Event(),
                    on_llm_retry=None, event_callback=None, run_timeout=60,
                )

        assert result is expected
        # 只应调用一次 resolve（第一个成功就停）
        assert service.llm_provider_service.resolve_llm_config.call_count == 1

    @pytest.mark.asyncio
    async def test_first_timeout_second_succeeds(self, service):
        """第一个备用超时，第二个成功 → 返回第二个的结果"""
        service.llm_provider_service.get_fallback_chain.return_value = [
            _entry("provider-a", "model-a"),
            _entry("provider-b", "model-b"),
        ]
        service.llm_provider_service.resolve_llm_config.return_value = MagicMock(
            context_window=128000,
        )

        expected_b = _make_result(result="备用 B 的答案")
        call_count = {"n": 0}

        with patch("app.services.agent_service.LLMAdapterFactory.create", return_value=MagicMock()):
            async def run_behavior(self, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    await asyncio.sleep(100)  # 第一个超时
                return expected_b  # 第二个成功

            with patch.object(RapidExecutionLoop, "run", run_behavior):
                result = await service._run_with_fallback(
                    task="test", task_content="test", project_path=None,
                    run_id="run-1", session_id="sess-1", history_messages=None,
                    agent_mode="build", original_loop=MagicMock(_last_context=None),
                    run_tool_registry=MagicMock(), cancel_event=asyncio.Event(),
                    on_llm_retry=None, event_callback=None, run_timeout=1,  # 1s 便于超时
                )

        assert result is expected_b
        assert call_count["n"] == 2  # 调用了两次

    @pytest.mark.asyncio
    async def test_all_fallbacks_timeout_returns_fallback_message(self, service):
        """备用链全部超时 → 返回兜底文案"""
        service.llm_provider_service.get_fallback_chain.return_value = [
            _entry("provider-a", "model-a"),
            _entry("provider-b", "model-b"),
        ]
        service.llm_provider_service.resolve_llm_config.return_value = MagicMock(
            context_window=128000,
        )

        with patch("app.services.agent_service.LLMAdapterFactory.create", return_value=MagicMock()):
            async def slow_run(self, **kwargs):
                await asyncio.sleep(100)
                return _make_result()

            with patch.object(RapidExecutionLoop, "run", slow_run):
                result = await service._run_with_fallback(
                    task="test", task_content="test", project_path=None,
                    run_id="run-1", session_id="sess-1", history_messages=None,
                    agent_mode="build", original_loop=MagicMock(_last_context=None),
                    run_tool_registry=MagicMock(), cancel_event=asyncio.Event(),
                    on_llm_retry=None, event_callback=None, run_timeout=1,
                )

        assert result.status == LoopStatus.COMPLETED
        assert "当前无可用模型" in result.result
