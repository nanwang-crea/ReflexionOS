"""
文件功能：RecordingLLM 录制适配器的单元测试
文件描述：验证透传无损（调用方收到的响应/chunk 序列与被包装适配器完全一致）、
         录制聚合正确（content/reasoning 拼接、工具调用保留、method 标记），
         以及关键的"stream_collect 提前关闭生成器时录制依然落盘"时序。
"""

from collections.abc import AsyncIterator

import pytest

from app.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    StreamChunk,
    UniversalLLMInterface,
)
from tests.support.recording_llm import RecordingLLM


class StubInnerLLM(UniversalLLMInterface):
    """返回固定内容的 stub 适配器，模拟真实 inner 的行为。"""

    def __init__(self, chunks: list[StreamChunk], complete_response: LLMResponse):
        """保存待播放的 chunk 流与 complete 响应。

        入参：chunks - stream_complete 将逐块产出的列表；
             complete_response - complete 将原样返回的响应。
        出参：无。
        """
        self._chunks = chunks
        self._complete_response = complete_response

    def get_model_name(self) -> str:
        """返回固定模型名。入参：无。出参：str。"""
        return "stub-model"

    async def complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> LLMResponse:
        """返回预置响应。入参：messages/tools（不消费）。出参：LLMResponse。"""
        return self._complete_response

    async def stream_complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """逐块产出预置 chunk 流。入参：messages/tools（不消费）。出参：chunk 迭代器。"""
        for chunk in self._chunks:
            yield chunk


class TestCompleteRecording:
    """C-01：complete 透传 + 录制"""

    @pytest.mark.asyncio
    async def test_complete_passthrough_and_record(self):
        """返回值与 inner 一致；录制列表新增 method="complete"、内容一致的条目。

        入参：无。出参：无。
        """
        inner_response = LLMResponse(
            content="真实响应",
            reasoning_content="推理",
            tool_calls=[LLMToolCall(id="c1", name="grep", arguments={"p": "x"})],
            finish_reason="tool_calls",
            model="stub-model",
            usage={"prompt_tokens": 3},
        )
        llm = RecordingLLM(StubInnerLLM([], inner_response))

        result = await llm.complete([])

        assert result is inner_response  # 透传：不改一字，同一对象
        assert len(llm.recorded) == 1
        entry = llm.recorded[0]
        assert entry.method == "complete"
        assert entry.content == "真实响应"
        assert entry.reasoning_content == "推理"
        assert entry.tool_calls[0].id == "c1"
        assert entry.tool_calls[0].arguments == {"p": "x"}
        assert entry.finish_reason == "tool_calls"
        assert entry.usage == {"prompt_tokens": 3}


class TestStreamRecording:
    """C-02：stream 透传 + 聚合录制"""

    @pytest.mark.asyncio
    async def test_stream_passthrough_and_aggregation(self):
        """调用方收到的 chunk 序列与 inner 产出完全一致；录制为聚合后的单条。

        入参：无。出参：无。
        """
        chunks = [
            StreamChunk(type="reasoning", reasoning_content="先想"),
            StreamChunk(type="content", content="前半"),
            StreamChunk(type="content", content="后半"),
            StreamChunk(type="done", finish_reason="stop"),
        ]
        llm = RecordingLLM(StubInnerLLM(chunks, LLMResponse()))

        received = [c async for c in llm.stream_complete([])]

        assert received == chunks  # 透传无损
        assert len(llm.recorded) == 1
        entry = llm.recorded[0]
        assert entry.method == "stream"
        assert entry.content == "前半后半"
        assert entry.reasoning_content == "先想"
        assert entry.tool_calls == []
        assert entry.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_tool_calls_terminal_recorded(self):
        """tool_calls 终止块：录制携带完整调用列表与 finish_reason。

        入参：无。出参：无。
        """
        chunks = [
            StreamChunk(
                type="tool_calls",
                tool_calls=[LLMToolCall(id="c9", name="glob", arguments={})],
                finish_reason="tool_calls",
            )
        ]
        llm = RecordingLLM(StubInnerLLM(chunks, LLMResponse()))

        received = [c async for c in llm.stream_complete([])]

        assert len(received) == 1
        assert llm.recorded[0].tool_calls[0].id == "c9"
        assert llm.recorded[0].finish_reason == "tool_calls"

    @pytest.mark.asyncio
    async def test_record_survives_stream_collect_early_close(self):
        """关键时序：经基类 stream_collect 消费（拿到终止块即 break + aclose
        生成器）时，录制仍须在生成器被关闭前落盘。

        入参：无。出参：无。
        """
        chunks = [
            StreamChunk(type="content", content="内容"),
            StreamChunk(type="done", finish_reason="stop"),
        ]
        llm = RecordingLLM(StubInnerLLM(chunks, LLMResponse()))

        response, _ = await llm.stream_collect([])

        assert response.content == "内容"
        assert len(llm.recorded) == 1  # 提前关闭也已完成录制
        assert llm.recorded[0].content == "内容"

    @pytest.mark.asyncio
    async def test_error_chunk_not_recorded(self):
        """error 块透传但不落录制（错误调用不属于完整调用）。

        入参：无。出参：无。
        """
        chunks = [StreamChunk(type="error", error="boom")]
        llm = RecordingLLM(StubInnerLLM(chunks, LLMResponse()))

        received = [c async for c in llm.stream_complete([])]

        assert received == chunks
        assert llm.recorded == []
