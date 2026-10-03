"""
文件功能：ReplayLLM 假模型适配器的单元测试
文件描述：覆盖回放播放的核心行为——顺序播放、流式切块、工具调用终止块、
         stream_collect 基类聚合（与真实主循环调用路径的接口校验）、
         method 漂移检测、超量调用与消费未尽检测。
"""

import pytest

from app.llm.base import LLMResponse
from tests.support.replay_fixture import ReplayFixture
from tests.support.replay_llm import (
    REPLAY_CHUNK_SIZE,
    ReplayExhaustedError,
    ReplayLLM,
    ReplayMismatchError,
)


def _fixture_with(responses: list[dict]) -> ReplayFixture:
    """用最简结构构造只含给定响应列表的夹具。

    入参：responses (list[dict]) - RecordedResponse 的 dict 形式列表。
    出参：ReplayFixture - 测试用夹具。
    """
    return ReplayFixture.model_validate(
        {
            "scenario": "unit-test",
            "model": "test-model",
            "responses": responses,
            "expected": {"loop_status": "completed", "event_sequence": []},
        }
    )


class TestCompletePlayback:
    """R-01：complete 路径顺序播放"""

    @pytest.mark.asyncio
    async def test_complete_returns_responses_in_order(self):
        """连续两次 complete 调用应按录制顺序返回两条响应。

        入参：无。出参：无（断言即验证）。
        """
        llm = ReplayLLM(
            _fixture_with(
                [
                    {"method": "complete", "content": "第一条"},
                    {"method": "complete", "content": "第二条"},
                ]
            )
        )

        r1 = await llm.complete([])
        r2 = await llm.complete([])

        assert r1.content == "第一条"
        assert r2.content == "第二条"
        assert r1.model == "test-model"
        llm.assert_fully_consumed()


class TestStreamPlayback:
    """R-02 / R-03：stream 路径切块与终止块"""

    @pytest.mark.asyncio
    async def test_stream_splits_content_into_fixed_chunks(self):
        """45 字符正文应切为 20+20+5 三个 content 块 + 一个 done 终止块。

        入参：无。出参：无。
        """
        content = "x" * (REPLAY_CHUNK_SIZE * 2 + 5)
        llm = ReplayLLM(
            _fixture_with([{"method": "stream", "content": content}])
        )

        chunks = [c async for c in llm.stream_complete([])]

        content_chunks = [c for c in chunks if c.type == "content"]
        assert [len(c.content) for c in content_chunks] == [
            REPLAY_CHUNK_SIZE,
            REPLAY_CHUNK_SIZE,
            5,
        ]
        assert chunks[-1].type == "done"
        assert chunks[-1].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_stream_tool_calls_terminal_chunk(self):
        """含工具调用的响应应以 tool_calls 终止块收尾并携带完整调用列表。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with(
                [
                    {
                        "method": "stream",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "name": "grep",
                                "arguments": {"pattern": "class"},
                            }
                        ],
                        "finish_reason": "tool_calls",
                    }
                ]
            )
        )

        chunks = [c async for c in llm.stream_complete([])]

        assert chunks[-1].type == "tool_calls"
        assert chunks[-1].finish_reason == "tool_calls"
        assert len(chunks[-1].tool_calls) == 1
        assert chunks[-1].tool_calls[0].id == "call_1"
        assert chunks[-1].tool_calls[0].name == "grep"
        assert chunks[-1].tool_calls[0].arguments == {"pattern": "class"}

    @pytest.mark.asyncio
    async def test_reasoning_emitted_before_content(self):
        """推理内容块应先于正文块产出（对齐真实推理模型输出顺序）。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with(
                [
                    {
                        "method": "stream",
                        "reasoning_content": "想一下",
                        "content": "结论",
                    }
                ]
            )
        )

        types = [c.type async for c in llm.stream_complete([])]

        assert types == ["reasoning", "content", "done"]


class TestStreamCollectIntegration:
    """R-04（关键）：基类 stream_collect 能正确聚合 ReplayLLM 的 chunk 流——
    这是与真实主循环调用路径（_call_llm 走 stream_collect）的接口校验。"""

    @pytest.mark.asyncio
    async def test_stream_collect_aggregates_content_and_tool_calls(self):
        """stream_collect 聚合结果应与夹具记录一致（正文拼接、工具调用完整）。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with(
                [
                    {
                        "method": "stream",
                        "reasoning_content": "推理片段",
                        "content": "这是一段用于验证聚合逻辑的完整正文内容",
                        "tool_calls": [],
                        "finish_reason": "stop",
                    },
                    {
                        "method": "stream",
                        "tool_calls": [
                            {"id": "call_9", "name": "glob", "arguments": {"p": "*"}}
                        ],
                        "finish_reason": "tool_calls",
                    },
                ]
            )
        )

        response1, _ = await llm.stream_collect([])
        assert isinstance(response1, LLMResponse)
        assert response1.content == "这是一段用于验证聚合逻辑的完整正文内容"
        assert response1.reasoning_content == "推理片段"
        assert response1.finish_reason == "stop"
        assert not response1.has_tool_calls

        response2, _ = await llm.stream_collect([])
        assert response2.has_tool_calls
        assert response2.tool_calls[0].id == "call_9"
        assert response2.finish_reason == "tool_calls"

        llm.assert_fully_consumed()

    @pytest.mark.asyncio
    async def test_stream_collect_invokes_content_callback(self):
        """stream_collect 的 on_content 回调应被逐块触发（对应 llm:content 事件路径）。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with(
                [{"method": "stream", "content": "y" * (REPLAY_CHUNK_SIZE + 1)}]
            )
        )
        pushed: list[str] = []

        async def on_content(piece: str) -> None:
            """收集 on_content 推送的文本块。入参：piece（单块文本）。出参：无。"""
            pushed.append(piece)

        response, _ = await llm.stream_collect([], on_content=on_content)

        assert len(pushed) == 2  # 20 + 1 两块
        assert "".join(pushed) == response.content


class TestMismatchAndExhaustion:
    """R-05 / R-06 / R-07 / R-08：漂移与消费量校验"""

    @pytest.mark.asyncio
    async def test_method_mismatch_raises(self):
        """录制为 stream 却调用 complete，应抛 ReplayMismatchError。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with([{"method": "stream", "content": "x"}])
        )

        with pytest.raises(ReplayMismatchError, match="漂移"):
            await llm.complete([])

    @pytest.mark.asyncio
    async def test_excess_call_raises_exhausted(self):
        """夹具只有 1 条响应，第 2 次调用应抛 ReplayExhaustedError。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with([{"method": "complete", "content": "仅一条"}])
        )
        await llm.complete([])

        with pytest.raises(ReplayExhaustedError, match="超过录制"):
            await llm.complete([])

    @pytest.mark.asyncio
    async def test_assert_fully_consumed_with_remainder_raises(self):
        """2 条响应只消费 1 条时，assert_fully_consumed 应抛错并注明剩余 1 条。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with(
                [
                    {"method": "complete", "content": "一"},
                    {"method": "complete", "content": "二"},
                ]
            )
        )
        await llm.complete([])  # 消费 1 条，剩余 1 条

        with pytest.raises(ReplayExhaustedError, match="1 条"):
            llm.assert_fully_consumed()

    @pytest.mark.asyncio
    async def test_assert_fully_consumed_passes_when_drained(self):
        """恰好消费完时 assert_fully_consumed 正常返回。

        入参：无。出参：无。
        """
        llm = ReplayLLM(
            _fixture_with([{"method": "complete", "content": "一"}])
        )
        await llm.complete([])

        llm.assert_fully_consumed()  # 不抛错即通过
