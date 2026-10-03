"""
文件功能：录制测试用的包装适配器（RecordingLLM）
文件描述：实现 UniversalLLMInterface，包装一个真实适配器——所有调用原样透传，
         同时把每次调用的聚合响应追加到内部录制列表，供回放夹具生成使用。
         仅用于开发期录制/重录夹具（record_replay_fixture.py），不进生产链路。
核心逻辑：
  - complete：透传后直接录制完整响应（method="complete"）；
  - stream_complete：逐块透传 inner 的 chunk（调用方看到的流与直连真实
    适配器完全一致），同时按 stream_collect 的同款聚合逻辑累积正文/推理/
    工具调用；遇到终止块（tool_calls / done）时落一条录制（method="stream"）；
  - 聚合逻辑刻意与 UniversalLLMInterface.stream_collect 保持一致，
    使"录制时聚合的结果"等于"回放时主循环将收集到的结果"。
注意点：流式调用中途被取消/出错（未见终止块）时不落录制——只记录完整调用。
"""

from collections.abc import AsyncIterator

from app.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    StreamChunk,
    UniversalLLMInterface,
)
from tests.support.replay_fixture import RecordedResponse, RecordedToolCall


class RecordingLLM(UniversalLLMInterface):
    """包装真实适配器：透传所有调用，每次完整响应追加到录制列表。"""

    def __init__(self, inner: UniversalLLMInterface):
        """以被包装的真实适配器初始化。

        入参：inner (UniversalLLMInterface) - 实际执行 LLM 调用的适配器。
        功能：保存 inner 引用，初始化空的录制列表 recorded
             （元素为 RecordedResponse，按调用顺序追加）。
        出参：无。
        """
        self.inner = inner
        self.recorded: list[RecordedResponse] = []

    def get_model_name(self) -> str:
        """透传模型名。

        入参：无。
        出参：str - inner 的模型名称。
        """
        return self.inner.get_model_name()

    async def complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> LLMResponse:
        """非流式补全：透传 inner，录制完整响应后返回。

        入参：messages / tools - 与真实接口一致，原样转发。
        出参：LLMResponse - inner 的原始返回（不改一字）。
        """
        response = await self.inner.complete(messages, tools)
        self.recorded.append(
            RecordedResponse(
                method="complete",
                content=response.content,
                reasoning_content=response.reasoning_content,
                tool_calls=self._to_recorded_tool_calls(response.tool_calls),
                finish_reason=response.finish_reason,
                usage=dict(response.usage),
            )
        )
        return response

    async def stream_complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """流式补全：逐块透传 inner 的 chunk，并在终止块处落一条录制。

        入参：messages / tools - 与真实接口一致，原样转发。
        功能：聚合逻辑与 stream_collect 一致——content/reasoning 块只累积文本，
             tool_calls / done 为终止块（落录制后结束），error 块不落录制
             （错误调用不属于"完整调用"，交给调用方的重试逻辑处理）。
        注意：录制必须发生在 yield 终止块**之前**——stream_collect 消费到
             终止块后会 break 并 aclose 本生成器，GeneratorExit 会从 yield
             点抛入，yield 之后的代码不会再执行。
        出参：AsyncIterator[StreamChunk] - 与 inner 产出完全一致的块序列。
        """
        content_parts: list[str] = []
        reasoning_parts: list[str] = []

        async for chunk in self.inner.stream_complete(messages, tools):
            if chunk.type == "content" and chunk.content:
                content_parts.append(chunk.content)
                yield chunk
                continue
            if chunk.type == "reasoning" and chunk.reasoning_content:
                reasoning_parts.append(chunk.reasoning_content)
                yield chunk
                continue
            if chunk.type in ("tool_calls", "done"):
                tool_calls = (
                    chunk.tool_calls if chunk.type == "tool_calls" else []
                )
                finish_reason = chunk.finish_reason or (
                    "tool_calls" if chunk.type == "tool_calls" else "stop"
                )
                # 先落录制再 yield：消费方拿到终止块即可能关闭本生成器
                self.recorded.append(
                    RecordedResponse(
                        method="stream",
                        content="".join(content_parts) or None,
                        reasoning_content="".join(reasoning_parts) or None,
                        tool_calls=self._to_recorded_tool_calls(tool_calls),
                        finish_reason=finish_reason,
                    )
                )
                yield chunk
                return
            # error 块（及未知类型块）：不录制，原样透传
            yield chunk
            if chunk.type == "error":
                return

    @staticmethod
    def _to_recorded_tool_calls(
        tool_calls: list[LLMToolCall],
    ) -> list[RecordedToolCall]:
        """把运行时工具调用列表转为可序列化的录制结构。

        入参：tool_calls (list[LLMToolCall]) - 运行时工具调用列表。
        出参：list[RecordedToolCall] - 录制用结构列表（保持 id/name/arguments）。
        """
        return [
            RecordedToolCall(id=tc.id, name=tc.name, arguments=dict(tc.arguments))
            for tc in tool_calls
        ]
