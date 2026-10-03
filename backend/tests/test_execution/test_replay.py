"""
文件功能：录制回放测试的端到端场景用例（E-01 / E-02 / E-03）
文件描述：用 ReplayLLM 驱动真实 RapidExecutionLoop 完整回放三个核心场景——
         纯问答直接完成、一次只读工具调用后完成、工具异常后恢复完成。
         断言归一化事件序列与 LoopResult 终态同夹具基线一致，
         且夹具响应恰好全部消费（由 run_scenario 内部强校验）。
注意点：tool-call-then-complete 使用真实 GrepTool 作用于 tmp_path 准备的
        文件树（经 PathSecurity 放行），夹具中的 "${WORK_DIR}" 占位符由
        run_scenario 的 variables 替换，保证夹具跨平台、与运行环境无关。
"""

from pathlib import Path
from typing import Any

import pytest

from app.security.path_security import PathSecurity
from app.execution.models import StepStatus
from app.tools.base import BaseTool, ToolApprovalRequest, ToolResult
from app.tools.grep_tool import GrepTool
from app.tools.registry import ToolRegistry
from tests.support.replay_harness import assert_replay, run_scenario

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "replay"


class ExplodingTool(BaseTool):
    """执行时必抛异常的受控故障工具，用于覆盖 tool:error 恢复路径。"""

    @property
    def name(self) -> str:
        """工具名。入参：无。出参：str - 固定为 explode。"""
        return "explode"

    @property
    def description(self) -> str:
        """工具描述。入参：无。出参：str - 固定文案。"""
        return "A tool that always raises during execution (test double)"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """直接抛出运行时异常，模拟工具执行期故障。

        入参：args (dict) - 调用参数（不消费）。
        出参：无（永不返回，总是抛出 RuntimeError）。
        """
        raise RuntimeError("boom")


class ApprovalTool(BaseTool):
    """必触发审批的受控工具：返回 approval_required，把决策权交给审批流。

    approval_id 固定为 "approval-1"，保证回放夹具的确定性
    （决策脚本与 approval:required 事件负载按 approval_id 关联）。
    """

    @property
    def name(self) -> str:
        """工具名。入参：无。出参：str - 固定为 approval_tool。"""
        return "approval_tool"

    @property
    def description(self) -> str:
        """工具描述。入参：无。出参：str - 固定文案。"""
        return "A tool that always requires approval (test double)"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """不真正执行，直接返回待审批结果。

        入参：args (dict) - 调用参数（原样记入审批 payload）。
        出参：ToolResult - approval_required=True 的待审批结果。
        """
        return ToolResult(
            success=False,
            approval_required=True,
            approval=ToolApprovalRequest(
                approval_id="approval-1",
                tool_name=self.name,
                summary="需要审批",
                payload=dict(args),
            ),
        )


class ConcurrentApprovalTool(BaseTool):
    """挂名只读工具（grep）的审批替身：让审批请求进入只读批次的
    asyncio.gather 并行路径（rapid_loop.py:443），从而构造"同一批次
    多个审批并发挂起"的场景。

    为什么必须叫 grep：tool_call_executor.py:83 的只读判定走白名单
    （grep/glob/session_recall），自定义名字会被归为写操作串行执行，
    永远凑不出并发审批。注册表是测试内新建的空表，不遮蔽真实 GrepTool。

    approval_id 从 args["pattern"] 派生（approval-a / approval-b），
    保证同批次两个审批各占独立槽位、不与 ApprovalTool 的固定 id 混淆。
    """

    @property
    def name(self) -> str:
        """工具名。入参：无。出参：str - 固定为 grep（进入只读白名单）。"""
        return "grep"

    @property
    def description(self) -> str:
        """工具描述。入参：无。出参：str - 固定文案。"""
        return "Read-only-named double that requires approval (test double)"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """不真正执行，直接返回待审批结果（approval_id 按 pattern 派生）。

        入参：args (dict) - 调用参数，须含 pattern 以派生 approval_id。
        出参：ToolResult - approval_required=True 的待审批结果。
        """
        return ToolResult(
            success=False,
            approval_required=True,
            approval=ToolApprovalRequest(
                approval_id=f"approval-{args.get('pattern', 'x')}",
                tool_name=self.name,
                summary="需要审批",
                payload=dict(args),
            ),
        )


def _registry_with(*tools: BaseTool) -> ToolRegistry:
    """把若干工具实例注册进一个新注册表。

    入参：tools (BaseTool) - 可变长工具实例列表。
    出参：ToolRegistry - 装配完成的注册表。
    """
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


class TestReplayScenarios:
    """三个核心场景的端到端回放"""

    @pytest.mark.asyncio
    async def test_simple_completion(self):
        """E-01：纯问答，模型直接返回内容 → completed，全程无 tool:* 事件。

        入参：无。出参：无（断言即验证）。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "simple-completion.json",
            _registry_with(),
        )

        assert_replay(result, events, fixture.expected)
        event_types = [t for t, _ in events]
        assert not any(t.startswith("tool:") for t in event_types)
        assert "ReflexionOS" in (result.result or "")

    @pytest.mark.asyncio
    async def test_tool_call_then_complete(self, tmp_path):
        """E-02：grep 只读调用（真实 GrepTool 作用于临时文件树）→ 总结完成。

        入参：tmp_path (pytest 临时目录) - 预置一个含关键词的源码文件。
        出参：无。
        """
        (tmp_path / "main.py").write_text(
            "class ReflexionOS:\n    pass\n", encoding="utf-8"
        )
        registry = _registry_with(
            GrepTool(PathSecurity(allowed_base_paths=[str(tmp_path)]))
        )

        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "tool-call-then-complete.json",
            registry,
            variables={"WORK_DIR": str(tmp_path)},
        )

        assert_replay(result, events, fixture.expected)
        tool_results = [p for t, p in events if t == "tool:result"]
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is True

    @pytest.mark.asyncio
    async def test_tool_error_recovery(self):
        """E-03：工具抛异常 → tool:error → 循环恢复并完成。

        入参：无。出参：无。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "tool-error-recovery.json",
            _registry_with(ExplodingTool()),
        )

        assert_replay(result, events, fixture.expected)
        tool_errors = [p for t, p in events if t == "tool:error"]
        assert len(tool_errors) == 1
        assert "boom" in (tool_errors[0]["error"] or "")

    @pytest.mark.asyncio
    async def test_approval_approve_then_complete(self):
        """E-04：审批批准路径——tool:result(success=True) + run:resuming，最终完成。

        入参：无。出参：无。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "approval-approve-then-complete.json",
            _registry_with(ApprovalTool()),
        )

        assert_replay(result, events, fixture.expected)
        tool_results = [p for t, p in events if t == "tool:result"]
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is True
        assert tool_results[0]["output"] == "审批通过后的工具输出"

    @pytest.mark.asyncio
    async def test_approval_reject_then_recover(self):
        """E-05：审批拒绝路径——tool:error('审批被拒绝') + run:resuming(approval_rejected)。

        入参：无。出参：无。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "approval-reject-then-recover.json",
            _registry_with(ApprovalTool()),
        )

        assert_replay(result, events, fixture.expected)
        tool_errors = [p for t, p in events if t == "tool:error"]
        assert len(tool_errors) == 1
        assert tool_errors[0]["error"] == "审批被拒绝"
        resuming = [p for t, p in events if t == "run:resuming"]
        assert len(resuming) == 1
        assert resuming[0]["approval_rejected"] is True

    @pytest.mark.asyncio
    async def test_approval_reject_exhaustion(self):
        """E-06：连续拒绝耗尽重试预算——前 5 次拒绝换路重试，
        第 6 次 turn_retries > MAX_TURN_RETRIES 转 FINAL_SUMMARY 强制总结。

        入参：无。出参：无。
        关键断言：run:resuming 恰好 5 次（第 6 次拒绝直接收尾，不再发
        resuming）；tool:error 恰好 6 次；总结阶段只有 summary:token
        没有 llm:content（_get_final_summary 直接调 stream_complete）。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "approval-reject-exhaustion.json",
            _registry_with(ApprovalTool()),
        )

        assert_replay(result, events, fixture.expected)
        tool_errors = [p for t, p in events if t == "tool:error"]
        assert len(tool_errors) == 6
        assert all(p["error"] == "审批被拒绝" for p in tool_errors)
        resuming = [p for t, p in events if t == "run:resuming"]
        assert len(resuming) == 5
        assert all(p["approval_rejected"] is True for p in resuming)
        assert result.result == "多次操作均未获批准，重试预算已耗尽，任务到此为止。"

    @pytest.mark.asyncio
    async def test_approval_concurrent_orphan(self):
        """E-07【缺陷快照 / characterization-of-bug】：并发只读批次多审批——
        主循环只处理首个等待步，第二个审批成为孤儿（approval:required 已发
        但槽位永不注册）。

        ⚠️ 本用例钉死的是**已确认的产品缺陷**（真实场景下前端可能弹出永远
        无法被响应的审批框、第二个操作无声消失），不是被认可的架构行为。
        立项跟踪见 项目问题报告.md「并发只读批次孤儿审批」——修复落地时
        本用例必须同步改写为期望行为（而非回滚修复）。

        入参：无。出参：无。
        关键断言：approval:required 恰好 2 次；run:waiting_for_approval /
        tool:result / run:resuming 各恰好 1 次（只对应首个审批）；
        孤儿步（call_pa_2）终态仍是 WAITING_FOR_APPROVAL。
        """
        result, events, fixture = await run_scenario(
            FIXTURE_DIR / "approval-concurrent-orphan.json",
            _registry_with(ConcurrentApprovalTool()),
        )

        assert_replay(result, events, fixture.expected)
        approvals = [p for t, p in events if t == "approval:required"]
        assert len(approvals) == 2
        assert [p["tool_call_id"] for p in approvals] == ["call_pa_1", "call_pa_2"]
        waiting = [p for t, p in events if t == "run:waiting_for_approval"]
        assert len(waiting) == 1
        orphan_steps = [
            s for s in result.steps if s.tool_call_id == "call_pa_2"
        ]
        assert len(orphan_steps) == 1
        assert orphan_steps[0].status == StepStatus.WAITING_FOR_APPROVAL
