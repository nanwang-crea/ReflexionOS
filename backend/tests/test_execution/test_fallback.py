# 文件功能：测试 Agent 运行兜底机制 —— 主 run 超时后切换备用模型继续完整循环
# 文件描述：覆盖三种场景：超时切备用成功、未配备用返回兜底文案、备用也超时返回兜底文案。
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.execution.models import LoopStatus
from app.execution.rapid_loop import RapidExecutionLoop
from app.services.agent_service import AgentService


def _make_fallback_result(status=LoopStatus.COMPLETED, result="备用模型结果"):
    """构造一个 LoopResult 模拟备用 loop 的返回"""
    from app.execution.models import LoopResult
    from datetime import datetime
    return LoopResult(
        id="run-fallback",
        task="test",
        status=status,
        result=result,
        created_at=datetime.now(),
    )


class TestRunWithFallback:
    """_run_with_fallback 行为测试"""

    @pytest.fixture
    def service(self):
        # mock 掉 AgentService 的底层依赖，只测 _run_with_fallback
        with patch.object(AgentService, "__init__", lambda self, **kw: None):
            svc = AgentService.__new__(AgentService)
            svc.llm_provider_service = MagicMock()
            return svc

    @pytest.mark.asyncio
    async def test_no_fallback_configured_returns_fallback_message(self, service):
        """未配备用模型 → 返回兜底文案 LoopResult"""
        service.llm_provider_service.get_fallback_selection.return_value = (None, None)

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
    async def test_fallback_timeout_returns_fallback_message(self, service):
        """备用模型也超时 → 返回兜底文案"""
        service.llm_provider_service.get_fallback_selection.return_value = (
            "provider-fb", "model-fb"
        )
        service.llm_provider_service.resolve_llm_config.return_value = MagicMock(
            provider_id="provider-fb",
            model_id="model-fb",
            context_window=128000,
        )

        # mock LLMAdapterFactory.create 返回一个 MagicMock adapter
        with patch("app.services.agent_service.LLMAdapterFactory.create", return_value=MagicMock()):
            # mock RapidExecutionLoop：run 被 wait_for 包到超时
            async def slow_run(self, **kwargs):
                await asyncio.sleep(100)  # 超过超时
                return _make_fallback_result()

            with patch.object(RapidExecutionLoop, "run", slow_run):
                result = await service._run_with_fallback(
                    task="test", task_content="test", project_path=None,
                    run_id="run-1", session_id="sess-1", history_messages=None,
                    agent_mode="build", original_loop=MagicMock(_last_context=None),
                    run_tool_registry=MagicMock(), cancel_event=asyncio.Event(),
                    on_llm_retry=None, event_callback=None, run_timeout=1,  # 用 1s 便于测试
                )

        assert result.status == LoopStatus.COMPLETED
        assert "当前无可用模型" in result.result

    @pytest.mark.asyncio
    async def test_fallback_succeeds_returns_fallback_result(self, service):
        """备用模型成功 → 返回备用 loop 的 LoopResult"""
        service.llm_provider_service.get_fallback_selection.return_value = (
            "provider-fb", "model-fb"
        )
        service.llm_provider_service.resolve_llm_config.return_value = MagicMock(
            provider_id="provider-fb",
            model_id="model-fb",
            context_window=128000,
        )

        expected_result = _make_fallback_result(result="备用模型给的答案")

        with patch("app.services.agent_service.LLMAdapterFactory.create", return_value=MagicMock()):
            async def quick_run(self, **kwargs):
                return expected_result

            with patch.object(RapidExecutionLoop, "run", quick_run):
                result = await service._run_with_fallback(
                    task="test", task_content="test", project_path=None,
                    run_id="run-1", session_id="sess-1", history_messages=None,
                    agent_mode="build", original_loop=MagicMock(_last_context=None),
                    run_tool_registry=MagicMock(), cancel_event=asyncio.Event(),
                    on_llm_retry=None, event_callback=None, run_timeout=60,
                )

        assert result is expected_result
        assert result.result == "备用模型给的答案"
