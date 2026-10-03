"""
文件功能：回放底座（replay_harness）的单元测试
文件描述：验证事件序列归一化规则（连续同类折叠）与基线断言行为
         （分叉定位输出、终态比对）。loop 组装的正确性由
         test_replay.py 的端到端场景覆盖，这里不重复测。
"""

import asyncio

import pytest

from app.execution.approval_flow import ApprovalFlow
from app.execution.models import LoopResult, LoopStatus
from tests.support.replay_fixture import ApprovalDecision, ExpectedOutcome
from tests.support.replay_harness import (
    _inject_when_slot_ready,
    _make_approval_aware_capture,
    assert_replay,
    normalize_event_types,
)


def _events(*types: str) -> list[tuple[str, dict]]:
    """把事件类型串转为捕获事件列表（负载填空 dict）。

    入参：types (str) - 可变长事件类型序列。
    出参：list[tuple[str, dict]] - 捕获事件列表。
    """
    return [(t, {}) for t in types]


def _result(status: LoopStatus) -> LoopResult:
    """构造指定终态的最简 LoopResult。

    入参：status (LoopStatus) - 目标终态。
    出参：LoopResult - 测试用结果对象。
    """
    return LoopResult(task="t", status=status)


class TestNormalizeEventTypes:
    """H-01 / H-02：连续同类事件折叠规则"""

    def test_folds_consecutive_duplicates(self):
        """[a,a,a,b,b,a] 应折叠为 [a,b,a]——首尾相同但不连续，不合并。

        入参：无。出参：无。
        """
        events = _events("a", "a", "a", "b", "b", "a")

        assert normalize_event_types(events) == ["a", "b", "a"]

    def test_no_duplicates_unchanged(self):
        """无连续重复时序列原样保留。

        入参：无。出参：无。
        """
        events = _events("a", "b", "c")

        assert normalize_event_types(events) == ["a", "b", "c"]

    def test_empty_sequence(self):
        """空事件序列归一化后仍为空。

        入参：无。出参：无。
        """
        assert normalize_event_types([]) == []


class TestAssertReplay:
    """H-03 / H-04：基线断言与分叉定位"""

    def test_matching_sequence_passes(self):
        """序列与终态都匹配时正常通过。

        入参：无。出参：无。
        """
        expected = ExpectedOutcome(
            loop_status="completed", event_sequence=["a", "b"]
        )

        assert_replay(_result(LoopStatus.COMPLETED), _events("a", "b"), expected)

    def test_divergence_reports_index_and_context(self):
        """第 3 条分叉时，断言消息应含分叉下标 2 及前后上下文窗口。

        入参：无。出参：无。
        """
        expected = ExpectedOutcome(
            loop_status="completed",
            event_sequence=["a", "b", "c", "d", "e"],
        )
        actual = _events("a", "b", "X", "d", "e")

        with pytest.raises(AssertionError, match="第一个分叉下标: 2") as exc_info:
            assert_replay(_result(LoopStatus.COMPLETED), actual, expected)

        message = str(exc_info.value)
        assert "'X'" in message  # 实际分叉点内容
        assert "'c'" in message  # 期望分叉点内容
        assert "实际全长" in message

    def test_length_mismatch_reported(self):
        """实际序列比期望短时也能定位（分叉下标为较短序列长度）。

        入参：无。出参：无。
        """
        expected = ExpectedOutcome(
            loop_status="completed", event_sequence=["a", "b", "c"]
        )

        with pytest.raises(AssertionError, match="第一个分叉下标: 2"):
            assert_replay(_result(LoopStatus.COMPLETED), _events("a", "b"), expected)

    def test_status_mismatch_reports_both_values(self):
        """终态不匹配时，断言消息应同时带出实际与期望状态值。

        入参：无。出参：无。
        """
        expected = ExpectedOutcome(
            loop_status="completed", event_sequence=["a"]
        )

        with pytest.raises(AssertionError, match="failed") as exc_info:
            assert_replay(_result(LoopStatus.FAILED), _events("a"), expected)

        assert "completed" in str(exc_info.value)


async def _noop_emit(event_type: str, data: dict) -> None:
    """空事件回调（ApprovalFlow 构造用）。入参：事件类型与负载。出参：无。"""


def _register_slot(flow: ApprovalFlow, approval_id: str) -> None:
    """模拟 wait_for_approval 注册审批槽位（测试便捷函数）。

    入参：flow - 审批流实例；approval_id - 槽位 id。
    出参：无。
    """

    flow._pending[approval_id] = (asyncio.Event(), None)


class TestApprovalDecisionInjector:
    """自动审批决策器：槽位等待时序 / 脚本耗尽 / id 错位"""

    @pytest.mark.asyncio
    async def test_inject_waits_for_late_slot_registration(self):
        """核心时序：槽位延迟注册时，决策器轮询等待并成功注入批准结果。

        入参：无。出参：无。
        """
        flow = ApprovalFlow(emit=_noop_emit)
        decision = ApprovalDecision(
            tool_call_id="c1", action="approve", output="批准输出", success=True
        )


        task = asyncio.create_task(_inject_when_slot_ready(flow, "a1", decision))
        await asyncio.sleep(0.05)  # 让决策器先轮询几轮（槽位尚不存在）
        _register_slot(flow, "a1")  # 模拟 wait_for_approval 晚到的槽位注册
        await task

        event, result = flow._pending["a1"]
        assert event.is_set()
        assert result == {"output": "批准输出", "error": None, "success": True}

    @pytest.mark.asyncio
    async def test_inject_reject_writes_none(self):
        """reject 决策向槽位写入 None（ApprovalFlow 语义：None 即拒绝）。

        入参：无。出参：无。
        """
        flow = ApprovalFlow(emit=_noop_emit)
        _register_slot(flow, "a1")
        decision = ApprovalDecision(tool_call_id="c1", action="reject")


        await _inject_when_slot_ready(flow, "a1", decision)

        event, result = flow._pending["a1"]
        assert event.is_set()
        assert result is None

    @pytest.mark.asyncio
    async def test_slot_never_registered_raises(self):
        """槽位始终不注册时，超时抛 AssertionError 并注明 approval_id。

        入参：无。出参：无。
        """

        import tests.support.replay_harness as harness

        flow = ApprovalFlow(emit=_noop_emit)
        decision = ApprovalDecision(tool_call_id="c1", action="approve")
        # 缩短超时避免测试慢（只影响本用例）
        original = harness._SLOT_WAIT_TIMEOUT
        harness._SLOT_WAIT_TIMEOUT = 0.05
        try:
            with pytest.raises(AssertionError, match="审批槽位未注册"):
                await _inject_when_slot_ready(flow, "ghost", decision)
        finally:
            harness._SLOT_WAIT_TIMEOUT = original

    @pytest.mark.asyncio
    async def test_decision_script_exhausted_raises(self):
        """决策队列空时再触发 approval:required，回调抛"决策脚本不足"。

        入参：无。出参：无。
        """
        flow = ApprovalFlow(emit=_noop_emit)
        capture, _queue, _tasks = _make_approval_aware_capture(
            [], lambda: flow, []
        )

        with pytest.raises(AssertionError, match="决策脚本不足"):
            await capture("approval:required", {"tool_name": "t", "tool_call_id": "c1"})

    @pytest.mark.asyncio
    async def test_tool_call_id_mismatch_raises(self):
        """决策的 tool_call_id 与事件负载不一致时抛错位错误，含两个 id。

        入参：无。出参：无。
        """
        flow = ApprovalFlow(emit=_noop_emit)
        decisions = [ApprovalDecision(tool_call_id="cX", action="approve")]
        capture, _queue, _tasks = _make_approval_aware_capture(
            [], lambda: flow, decisions
        )

        with pytest.raises(AssertionError, match="错位") as exc_info:
            await capture("approval:required", {"tool_call_id": "cY"})

        assert "cX" in str(exc_info.value)
        assert "cY" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_orphaned_decision_consumed_without_injection(self):
        """孤儿决策（expect_orphaned=True）：正常消费并校验 id，
        但不创建注入任务（并发批次非首个审批的槽位永不注册，
        创建注入任务只会轮询超时）。

        入参：无。出参：无。
        """
        flow = ApprovalFlow(emit=_noop_emit)
        decisions = [
            ApprovalDecision(
                tool_call_id="c1", action="approve", expect_orphaned=True
            )
        ]
        capture, queue, tasks = _make_approval_aware_capture(
            [], lambda: flow, decisions
        )

        await capture(
            "approval:required",
            {"tool_call_id": "c1", "approval_id": "a1"},
        )

        assert not queue  # 决策已消费
        assert not tasks  # 未创建注入任务
        assert "a1" not in flow._pending  # 未触碰审批流

    @pytest.mark.asyncio
    async def test_orphaned_decision_still_validates_call_id(self):
        """孤儿决策同样做 tool_call_id 校验——id 错位照常抛错。

        入参：无。出参：无。
        """
        flow = ApprovalFlow(emit=_noop_emit)
        decisions = [
            ApprovalDecision(
                tool_call_id="cX", action="approve", expect_orphaned=True
            )
        ]
        capture, _queue, _tasks = _make_approval_aware_capture(
            [], lambda: flow, decisions
        )

        with pytest.raises(AssertionError, match="错位"):
            await capture("approval:required", {"tool_call_id": "cY"})
