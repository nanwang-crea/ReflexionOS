"""循环级并行写操作测试：同一批内路径互不相同的 edit 调用真实并发执行，
同路径 / 混入 shell 的批次退化为串行。

使用 RecordingExecutor 替换 loop.tool_executor，以并发计数器验证峰值并发度。
"""
import asyncio
from unittest.mock import AsyncMock

import pytest
from app.execution.models import LoopStep, StepStatus
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm.base import LLMResponse, LLMToolCall, StreamChunk
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry


class _ChunkStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    async def aclose(self):
        return None


class RecordingExecutor:
    """记录并发度与调用顺序的假执行器：所有调用均成功完成。"""

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.active = 0
        self.peak = 0
        self.executed_paths: list[str] = []

    async def execute(self, tool_call, context, step_number) -> LoopStep:
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.executed_paths.append(str(tool_call.arguments.get("path")))
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        return LoopStep(
            step_number=step_number,
            tool=tool_call.name,
            tool_call_id=tool_call.id,
            args=tool_call.arguments,
            status=StepStatus.SUCCESS,
            output="ok",
            duration=self.delay,
        )

    def _is_read_only_call(self, tool_call) -> bool:
        return False

    def prepare_read_only_batch(self, tool_calls):
        return tool_calls


def build_tool_calls(specs: list[tuple[str, str]]) -> list[LLMToolCall]:
    return [
        LLMToolCall(id=f"call-{i}", name="edit", arguments={"action": action, "path": path})
        for i, (path, action) in enumerate(specs)
    ]


def build_llm(turns: list[list[LLMToolCall]]) -> AsyncMock:
    """按轮次返回预置响应的假 LLM：末轮之后固定返回纯文本结束。"""
    llm = AsyncMock()
    llm.get_model_name = lambda: "test-model"
    state = {"turn": 0}

    async def stream_complete(messages, tools=None):
        index = min(state["turn"], len(turns))
        state["turn"] += 1
        tool_calls = turns[index] if index < len(turns) else []
        if tool_calls:
            chunks = [StreamChunk(type="tool_calls", tool_calls=tool_calls, finish_reason="tool_calls")]
        else:
            chunks = [StreamChunk(type="content", content="全部完成"), StreamChunk(type="done", finish_reason="stop")]
        return LLMResponse(
            content="" if tool_calls else "全部完成",
            reasoning_content=None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            model="test-model",
        ), None

        async def _unused():  # pragma: no cover
            yield None

    llm.stream_complete = stream_complete

    async def stream_collect(messages, tools=None, *, on_content=None, on_reasoning=None, max_empty_retries=3, track_first_chunk_latency=False):
        response, _ = await stream_complete(messages, tools)
        return response, None

    llm.stream_collect = stream_collect
    return llm


def build_loop(llm) -> RapidExecutionLoop:
    loop = RapidExecutionLoop(llm=llm, tool_registry=ToolRegistry(), max_steps=8)
    loop.tool_executor = RecordingExecutor()
    return loop


@pytest.mark.asyncio
async def test_distinct_path_edit_batch_executes_concurrently():
    llm = build_llm([
        build_tool_calls([("/t/a.py", "str_replace"), ("/t/b.py", "write"), ("/t/c.py", "str_replace")]),
    ])
    loop = build_loop(llm)

    result = await loop.run("同时改三个文件")

    recorder = loop.tool_executor
    assert recorder.peak == 3  # 三条互不相同的路径真实并发
    assert recorder.executed_paths == ["/t/a.py", "/t/b.py", "/t/c.py"]
    assert all(step.status == StepStatus.SUCCESS for step in result.steps)


@pytest.mark.asyncio
async def test_same_path_edit_batch_stays_serial():
    llm = build_llm([
        build_tool_calls([("/t/a.py", "str_replace"), ("/t/a.py", "str_replace")]),
    ])
    loop = build_loop(llm)

    await loop.run("同文件连续编辑")

    assert loop.tool_executor.peak == 1  # 同路径退化为串行，保持编辑语义


@pytest.mark.asyncio
async def test_shell_mixed_batch_stays_serial():
    llm = build_llm([
        [
            LLMToolCall(id="call-0", name="edit", arguments={"action": "str_replace", "path": "/t/a.py"}),
            LLMToolCall(id="call-1", name="shell", arguments={"command": "ls"}),
            LLMToolCall(id="call-2", name="edit", arguments={"action": "str_replace", "path": "/t/b.py"}),
        ],
    ])
    loop = build_loop(llm)

    await loop.run("编辑夹命令")

    assert loop.tool_executor.peak == 1  # shell 是全局屏障，整批串行
    # 三次调用（两次 edit + 一次 shell 的 path 为 None）全部按序执行
    assert loop.tool_executor.executed_paths == ["/t/a.py", "None", "/t/b.py"]  # shell 的 path 记录为字符串 "None"
