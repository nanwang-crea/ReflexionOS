"""ApprovalFlow 多槽位并发行为测试。

覆盖场景：多个并发审批同时挂起时，各自独立等待、互不覆盖；
以及缺省 approval_id 时对单/多挂起场景的兼容行为。
"""
import asyncio

import pytest

from app.execution.approval_flow import ApprovalFlow
from app.execution.models import LoopStep, StepStatus


def _make_step(approval_id: str, tool: str = "shell") -> LoopStep:
    return LoopStep(
        step_number=1,
        tool=tool,
        tool_call_id=f"call-{approval_id}",
        approval_id=approval_id,
        args={},
        status=StepStatus.WAITING_FOR_APPROVAL,
    )


async def _noop_emit(event_type: str, data: dict) -> None:
    pass


class TestApprovalFlowConcurrency:
    @pytest.mark.asyncio
    async def test_two_concurrent_approvals_do_not_cross_talk(self):
        """两个并发审批同时挂起，各自 set_approval_result 后必须拿到各自对应的结果，不能串台。"""
        flow = ApprovalFlow(emit=_noop_emit)

        step_a = _make_step("approval-a")
        step_b = _make_step("approval-b")

        task_a = asyncio.create_task(flow.wait_for_approval(step_a, run_id="run-1"))
        task_b = asyncio.create_task(flow.wait_for_approval(step_b, run_id="run-1"))

        # 确保两者都已进入等待状态（槽位已注册）
        await asyncio.sleep(0.01)
        assert "approval-a" in flow._pending
        assert "approval-b" in flow._pending

        # 先批准 b，再拒绝 a —— 顺序刻意与创建顺序相反，验证不会按创建顺序错配
        flow.set_approval_result(
            {"success": True, "output": "b approved", "error": None},
            approval_id="approval-b",
        )
        flow.set_approval_result(None, approval_id="approval-a")

        result_a = await task_a
        result_b = await task_b

        assert result_a.approved is False
        assert result_b.approved is True
        assert result_b.output == "b approved"

    @pytest.mark.asyncio
    async def test_resolving_one_does_not_wake_other(self):
        """解决其中一个审批不应唤醒另一个仍在等待的审批。"""
        flow = ApprovalFlow(emit=_noop_emit)

        step_a = _make_step("approval-a")
        step_b = _make_step("approval-b")

        task_a = asyncio.create_task(flow.wait_for_approval(step_a, run_id="run-1"))
        task_b = asyncio.create_task(flow.wait_for_approval(step_b, run_id="run-1"))
        await asyncio.sleep(0.01)

        flow.set_approval_result(
            {"success": True, "output": "a done", "error": None}, approval_id="approval-a"
        )

        result_a = await asyncio.wait_for(task_a, timeout=1.0)
        assert result_a.approved is True

        # b 仍应处于挂起状态，未被 a 的结果误唤醒
        assert not task_b.done()
        assert "approval-b" in flow._pending

        flow.set_approval_result(None, approval_id="approval-b")
        result_b = await asyncio.wait_for(task_b, timeout=1.0)
        assert result_b.approved is False

    @pytest.mark.asyncio
    async def test_missing_approval_id_with_single_pending_falls_back(self):
        """兼容旧调用方：只有一个挂起槽位时，缺省 approval_id 应自动定位到它。"""
        flow = ApprovalFlow(emit=_noop_emit)
        step = _make_step("only-one")

        task = asyncio.create_task(flow.wait_for_approval(step, run_id="run-1"))
        await asyncio.sleep(0.01)

        flow.set_approval_result({"success": True, "output": "ok", "error": None})

        result = await asyncio.wait_for(task, timeout=1.0)
        assert result.approved is True
        assert result.output == "ok"

    @pytest.mark.asyncio
    async def test_missing_approval_id_with_multiple_pending_is_rejected(self):
        """存在多个并发挂起槽位时，缺省 approval_id 无法确定目标，结果应被丢弃且不影响任何一方。"""
        flow = ApprovalFlow(emit=_noop_emit)
        step_a = _make_step("approval-a")
        step_b = _make_step("approval-b")

        task_a = asyncio.create_task(flow.wait_for_approval(step_a, run_id="run-1"))
        task_b = asyncio.create_task(flow.wait_for_approval(step_b, run_id="run-1"))
        await asyncio.sleep(0.01)

        # 缺省 approval_id，且当前有两个挂起槽位 —— 应记录错误但不 set 任何一个事件
        flow.set_approval_result({"success": True, "output": "ambiguous", "error": None})

        await asyncio.sleep(0.01)
        assert not task_a.done()
        assert not task_b.done()

        # 清理：显式补上正确的 approval_id 让任务能正常结束
        flow.set_approval_result(None, approval_id="approval-a")
        flow.set_approval_result(None, approval_id="approval-b")
        await asyncio.wait_for(task_a, timeout=1.0)
        await asyncio.wait_for(task_b, timeout=1.0)

    @pytest.mark.asyncio
    async def test_unknown_approval_id_is_ignored(self):
        """对不存在的 approval_id 调用 set_approval_result 应被安全忽略，不抛异常。"""
        flow = ApprovalFlow(emit=_noop_emit)
        # 不应抛出异常
        flow.set_approval_result({"success": True}, approval_id="nonexistent")
        assert flow._pending == {}

    @pytest.mark.asyncio
    async def test_step_without_approval_id_returns_denied(self):
        """step.approval_id 缺失时应直接拒绝，不应挂起等待。"""
        flow = ApprovalFlow(emit=_noop_emit)
        step = LoopStep(
            step_number=1,
            tool="shell",
            tool_call_id="call-x",
            approval_id=None,
            args={},
            status=StepStatus.WAITING_FOR_APPROVAL,
        )
        result = await asyncio.wait_for(
            flow.wait_for_approval(step, run_id="run-1"), timeout=1.0
        )
        assert result.approved is False
