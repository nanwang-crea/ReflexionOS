"""
文件功能：回放底座（replay_harness）的单元测试
文件描述：验证事件序列归一化规则（连续同类折叠）与基线断言行为
         （分叉定位输出、终态比对）。loop 组装的正确性由
         test_replay.py 的端到端场景覆盖，这里不重复测。
"""

import pytest

from app.execution.models import LoopResult, LoopStatus
from tests.support.replay_fixture import ExpectedOutcome
from tests.support.replay_harness import assert_replay, normalize_event_types


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
