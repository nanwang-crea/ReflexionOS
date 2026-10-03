"""
文件功能：回放测试底座（replay_harness）
文件描述：把"加载夹具 → 组装 RapidExecutionLoop（ReplayLLM + 受控工具注册表 +
         事件捕获）→ 执行 run → 归一化事件序列 → 对照基线断言"这一整套回放
         流程封装成可复用函数，供 test_replay.py 的场景用例调用。
核心逻辑：
  - build_loop：以 ReplayLLM 驱动真实主循环，event_callback 替换为捕获器，
    把 (event_type, payload) 全部记录下来；
  - run_scenario：跑完 fixture.task 后强制 assert_fully_consumed，
    保证"LLM 调用次数与录制一致"也成为断言的一部分；
  - normalize_event_types：连续同类事件折叠为单条，降低基线对
    "模型把回复切成几块"这类无关细节的敏感度；
  - assert_replay：比对归一化序列与 LoopResult 终态，失败时给出第一个
    分叉下标及前后上下文，便于定位行为漂移点。
"""

from pathlib import Path

from app.execution.models import LoopResult
from app.execution.rapid_loop import RapidExecutionLoop
from app.tools.registry import ToolRegistry
from tests.support.replay_fixture import (
    ExpectedOutcome,
    ReplayFixture,
    load_fixture,
)
from tests.support.replay_llm import ReplayLLM

#  captured_events 的元素类型：(事件类型, 原始负载)
CapturedEvent = tuple[str, dict]


def build_loop(
    fixture: ReplayFixture,
    tool_registry: ToolRegistry,
    *,
    max_steps: int = 10,
) -> tuple[RapidExecutionLoop, ReplayLLM, list[CapturedEvent]]:
    """用回放夹具组装一个可捕获事件的真实主循环。

    入参：fixture (ReplayFixture) - 回放夹具；
         tool_registry (ToolRegistry) - 调用方按场景准备的受控工具注册表；
         max_steps (int) - 单 run 最大步数，默认 10（回放场景应远小于此值，
                          超限即说明行为漂移成死循环，让其自然失败）。
    功能：创建 ReplayLLM 与事件捕获列表，组装 RapidExecutionLoop；
         捕获回调是 async 的，与生产 event_callback 签名一致。
    出参：(loop, replay_llm, captured_events) 三元组——replay_llm 用于收尾
          校验消费量，captured_events 在 run 后被填充。
    """
    replay_llm = ReplayLLM(fixture)
    captured: list[CapturedEvent] = []

    async def capture(event_type: str, payload: dict) -> None:
        """事件捕获回调：把主循环发射的每个事件追加到 captured 列表。

        入参：event_type (str) - 事件类型；payload (dict) - 原始负载。
        出参：无。
        """
        captured.append((event_type, payload))

    loop = RapidExecutionLoop(
        llm=replay_llm,
        tool_registry=tool_registry,
        max_steps=max_steps,
        event_callback=capture,
    )
    return loop, replay_llm, captured


async def run_scenario(
    fixture_path: str | Path,
    tool_registry: ToolRegistry,
    *,
    max_steps: int = 10,
    variables: dict[str, str] | None = None,
) -> tuple[LoopResult, list[CapturedEvent], ReplayFixture]:
    """加载夹具并完整回放一个场景。

    入参：fixture_path (str | Path) - 夹具 JSON 路径；
         tool_registry (ToolRegistry) - 受控工具注册表；
         max_steps (int) - 单 run 最大步数；
         variables (dict[str, str] | None) - 变量替换表。夹具的工具调用参数中
             形如 "${KEY}" 的占位符会被替换为对应值——用于把 tmp_path 等
             运行时才能确定的路径注入夹具，保证夹具跨平台、与运行环境无关。
    功能：load_fixture → （可选）变量替换 → build_loop → loop.run(fixture.task)；
         run 结束后调用 replay_llm.assert_fully_consumed()，
         把"LLM 调用次数与录制完全一致"纳入断言。
    出参：(LoopResult, captured_events, fixture) 三元组，
          fixture 一并返回供调用方取 expected 做断言。
    异常：ReplayExhaustedError / ReplayMismatchError（消费量或调用入口漂移）。
    """
    fixture = load_fixture(fixture_path)
    if variables:
        _substitute_variables(fixture, variables)
    loop, replay_llm, captured = build_loop(
        fixture, tool_registry, max_steps=max_steps
    )

    result = await loop.run(fixture.task)
    replay_llm.assert_fully_consumed()

    return result, captured, fixture


def _substitute_variables(fixture: ReplayFixture, variables: dict[str, str]) -> None:
    """就地替换夹具全部工具调用参数中的 "${KEY}" 占位符。

    入参：fixture (ReplayFixture) - 待处理的夹具（就地修改其 responses）；
         variables (dict[str, str]) - 占位符替换表（键不含 ${} 包裹）。
    功能：递归遍历每个 RecordedToolCall.arguments，字符串值（含嵌套
         list/dict 中的字符串）中的 "${KEY}" 全部替换为 variables[KEY]；
         未在替换表中的占位符保持原样（留待断言阶段暴露，而非静默放行）。
    出参：无（就地修改）。
    """

    def _replace(value):
        """递归替换单个参数值中的占位符。

        入参：value - 任意 JSON 类型的参数值。
        出参：替换后的同类型值。
        """
        if isinstance(value, str):
            for key, replacement in variables.items():
                value = value.replace("${" + key + "}", replacement)
            return value
        if isinstance(value, list):
            return [_replace(item) for item in value]
        if isinstance(value, dict):
            return {k: _replace(v) for k, v in value.items()}
        return value

    for response in fixture.responses:
        for tool_call in response.tool_calls:
            tool_call.arguments = _replace(tool_call.arguments)


def normalize_event_types(events: list[CapturedEvent]) -> list[str]:
    """把捕获的事件序列归一化为事件类型序列（连续同类折叠为单条）。

    入参：events (list[CapturedEvent]) - run 期间捕获的 (type, payload) 列表。
    功能：只保留事件类型，丢弃负载（负载含 run_id、耗时、token 数等易变值）；
         连续重复的同类事件折叠为一条（如 llm:content ×5 → llm:content ×1），
         使基线不依赖"响应被切成几个流式块"这种无关细节。
    出参：list[str] - 归一化后的事件类型序列。
    """
    normalized: list[str] = []
    for event_type, _ in events:
        if not normalized or normalized[-1] != event_type:
            normalized.append(event_type)
    return normalized


def assert_replay(
    result: LoopResult,
    events: list[CapturedEvent],
    expected: ExpectedOutcome,
) -> None:
    """对照基线断言回放结果。

    入参：result (LoopResult) - 主循环执行结果；
         events (list[CapturedEvent]) - 捕获的原始事件序列；
         expected (ExpectedOutcome) - 夹具中的期望基线。
    功能：依次断言——① 归一化事件序列与 expected.event_sequence 完全一致
         （不一致时输出第一个分叉下标及前后各 3 条上下文）；
         ② result.status 的字符串值与 expected.loop_status 一致。
    出参：无（断言失败抛 AssertionError）。
    """
    actual = normalize_event_types(events)
    want = expected.event_sequence

    if actual != want:
        divergence = next(
            (i for i, (a, w) in enumerate(zip(actual, want)) if a != w),
            min(len(actual), len(want)),
        )
        lo = max(0, divergence - 3)
        hi = divergence + 4
        context_lines = [
            f"第一个分叉下标: {divergence}",
            f"实际[{lo}:{hi}]: {actual[lo:hi]}",
            f"期望[{lo}:{hi}]: {want[lo:hi]}",
            f"实际全长 {len(actual)} 条，期望全长 {len(want)} 条",
        ]
        raise AssertionError(
            "回放事件序列与基线不一致：\n" + "\n".join(context_lines)
        )

    actual_status = (
        result.status.value if hasattr(result.status, "value") else str(result.status)
    )
    assert actual_status == expected.loop_status, (
        f"LoopResult 终态与基线不一致：实际 {actual_status}，"
        f"期望 {expected.loop_status}"
    )
