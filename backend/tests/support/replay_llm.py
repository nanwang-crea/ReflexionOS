"""
文件功能：回放测试用的假模型适配器（ReplayLLM）
文件描述：实现 UniversalLLMInterface，按夹具（ReplayFixture）中录制的顺序逐条
         播放 LLM 响应，使 RapidExecutionLoop 无需真实 API key 即可完整回放
         一次任务执行。是录制回放测试（record-replay）的核心组件。
核心逻辑：
  - complete / stream_complete 每次被调用时从响应队列弹出下一条录制响应，
    并校验"被调用的方法"与录制的 method 标记一致（不一致说明主循环换了
    LLM 调用入口，属行为漂移，直接报错）；
  - stream_complete 把录制的完整响应切成定长小块逐块 yield，模拟真实流式
    输出，保证 llm:content 等流式事件被真实触发；
  - 队列消费完毕仍被调用 → ReplayExhaustedError；
  - 测试结束调 assert_fully_consumed 校验"恰好消费完"——有剩余说明主循环
    提前退出，消费超量说明产生了多余调用。
注意点：基类 stream_collect 对"空响应"（无正文且无工具调用）会自动重试
        （最多 max_empty_retries 次），会额外消耗队列条目——夹具作者应避免
        录制空响应，或把重试消耗计入预期。
"""

from collections import deque
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    StreamChunk,
    UniversalLLMInterface,
)

if TYPE_CHECKING:
    from tests.support.replay_fixture import ReplayFixture, RecordedResponse

# 流式回放时正文/推理内容的切块大小（字符数）。
# 取一个远小于真实响应长度的固定值，让一次回放产生多次流式事件，
# 覆盖前端的增量渲染路径；固定常量保证回放确定性。
REPLAY_CHUNK_SIZE = 20


class ReplayExhaustedError(RuntimeError):
    """回放队列已空但仍被调用——实际 LLM 调用次数超过录制次数。"""


class ReplayMismatchError(RuntimeError):
    """实际调用的方法与录制标记不符——主循环的 LLM 调用入口发生了漂移。"""


class ReplayLLM(UniversalLLMInterface):
    """按夹具顺序播放预录响应的假模型，用于 keyless 回放测试。"""

    def __init__(self, fixture: "ReplayFixture"):
        """以夹具初始化回放队列。

        入参：fixture (ReplayFixture) - 回放夹具，responses 按调用顺序排列。
        功能：复制响应列表到内部双端队列（不改动传入夹具对象），
             记录模型名供 get_model_name 返回。
        出参：无。
        """
        self._queue: deque = deque(fixture.responses)
        self._model = fixture.model

    def get_model_name(self) -> str:
        """返回夹具记录的模型名。

        入参：无。
        出参：str - 录制时的模型名称。
        """
        return self._model

    async def complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> LLMResponse:
        """非流式补全：弹出下一条录制响应（须为 method="complete"）并返回。

        入参：messages / tools - 与真实接口一致，回放中不消费（响应已预录）。
        出参：LLMResponse - 录制的响应，model 字段补为夹具模型名。
        异常：ReplayExhaustedError（队列空）、ReplayMismatchError（method 不符）。
        """
        recorded = self._pop_expected("complete")
        return LLMResponse(
            content=recorded.content,
            reasoning_content=recorded.reasoning_content,
            tool_calls=self._to_tool_calls(recorded),
            finish_reason=recorded.finish_reason,
            model=self._model,
            usage=dict(recorded.usage),
        )

    async def stream_complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """流式补全：弹出下一条录制响应（须为 method="stream"），切块逐块产出。

        入参：messages / tools - 与真实接口一致，回放中不消费。
        功能：先把 reasoning_content、content 按 REPLAY_CHUNK_SIZE 切块逐块
             yield（先推理后正文，对齐真实推理模型的输出顺序）；再 yield 一个
             终止块——有工具调用时为 type="tool_calls"（携带完整调用列表），
             否则为 type="done"，均带上录制的 finish_reason。
        出参：AsyncIterator[StreamChunk] - 流式块序列。
        异常：ReplayExhaustedError（队列空）、ReplayMismatchError（method 不符）。
        """
        recorded = self._pop_expected("stream")

        for piece in self._split(recorded.reasoning_content):
            yield StreamChunk(type="reasoning", reasoning_content=piece)
        for piece in self._split(recorded.content):
            yield StreamChunk(type="content", content=piece)

        tool_calls = self._to_tool_calls(recorded)
        if tool_calls:
            yield StreamChunk(
                type="tool_calls",
                tool_calls=tool_calls,
                finish_reason=recorded.finish_reason or "tool_calls",
            )
        else:
            yield StreamChunk(
                type="done", finish_reason=recorded.finish_reason or "stop"
            )

    def assert_fully_consumed(self) -> None:
        """校验夹具响应恰好全部消费完。

        入参：无。
        功能：队列仍有剩余说明主循环比录制时少调了 LLM（提前退出/分支变化），
             抛 ReplayExhaustedError 并注明剩余条数；无剩余则正常返回。
        出参：无。
        异常：ReplayExhaustedError - 队列存在未消费的录制响应。
        """
        if self._queue:
            raise ReplayExhaustedError(
                f"回放结束时仍有 {len(self._queue)} 条录制响应未消费，"
                "主循环的 LLM 调用次数少于录制次数"
            )

    def _pop_expected(self, method: str) -> "RecordedResponse":
        """从队列弹出下一条录制响应并校验方法标记。

        入参：method (str) - 实际被调用的方法（"complete" 或 "stream"）。
        出参：RecordedResponse - 下一条录制响应。
        异常：ReplayExhaustedError（队列空）；ReplayMismatchError（method 不符，
             消息中带出期望与实际值，便于定位漂移点）。
        """
        if not self._queue:
            raise ReplayExhaustedError(
                "回放队列已空，主循环的 LLM 调用次数超过录制次数"
            )
        recorded = self._queue.popleft()
        if recorded.method != method:
            raise ReplayMismatchError(
                f"LLM 调用入口漂移：录制为 {recorded.method}，"
                f"实际调用为 {method}（第若干次调用，剩余 {len(self._queue)} 条）"
            )
        return recorded

    @staticmethod
    def _to_tool_calls(recorded: "RecordedResponse") -> list[LLMToolCall]:
        """把录制的工具调用转换为运行时 LLMToolCall 列表。

        入参：recorded (RecordedResponse) - 一条录制响应。
        出参：list[LLMToolCall] - 运行时工具调用列表（保持录制 id/name/arguments）。
        """
        return [
            LLMToolCall(id=tc.id, name=tc.name, arguments=dict(tc.arguments))
            for tc in recorded.tool_calls
        ]

    @staticmethod
    def _split(text: str | None) -> list[str]:
        """把文本按 REPLAY_CHUNK_SIZE 切成定长小块。

        入参：text (str | None) - 待切块文本，None 或空串返回空列表。
        出参：list[str] - 按序排列的文本块。
        """
        if not text:
            return []
        return [
            text[i : i + REPLAY_CHUNK_SIZE]
            for i in range(0, len(text), REPLAY_CHUNK_SIZE)
        ]
