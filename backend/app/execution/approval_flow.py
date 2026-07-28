"""审批流 — 只负责等待/接收审批结果，返回结构化 ApprovalResult。"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.execution.models import LoopStep

logger = logging.getLogger(__name__)


@dataclass
class ApprovalResult:
    """审批交互的结构化结果。"""

    approved: bool
    output: str | None = None
    error: str | None = None
    success: bool = False
    observability: dict | None = None


class ApprovalFlow:
    """
    审批流 — 只负责等待/接收审批结果，返回结构化 ApprovalResult。
    不负责：tool 执行、状态转移、事件发送。

    多槽位设计：按 approval_id 存储独立的 (Event, result) 槽位，
    支持多个并发审批同时挂起（如并行 delegate 场景下多个子 agent
    同时触发审批），互不覆盖、各自等待各自的结果。
    """

    def __init__(self, emit: Callable[[str, dict], Awaitable[None]]):
        self._emit = emit
        # approval_id -> (等待事件, 审批结果)。结果在 set 之前为 None。
        self._pending: dict[str, tuple[asyncio.Event, dict | None]] = {}

    def set_approval_result(
        self, result: dict | None, approval_id: str | None = None
    ) -> None:
        """
        外部调用：审批结果写入。

        approval_id 缺省时（兼容旧调用方/单审批场景）：若当前只有一个挂起的
        审批槽位则自动定位到它；若有多个挂起槽位则无法确定目标，记录错误并丢弃。
        """
        target_id = approval_id
        if target_id is None:
            if len(self._pending) == 1:
                target_id = next(iter(self._pending))
            elif len(self._pending) == 0:
                logger.warning("[ApprovalFlow] set_approval_result: 无挂起的审批槽位，结果被丢弃")
                return
            else:
                logger.error(
                    "[ApprovalFlow] set_approval_result: 存在 %d 个并发挂起的审批，"
                    "必须显式传入 approval_id，结果被丢弃",
                    len(self._pending),
                )
                return

        slot = self._pending.get(target_id)
        if slot is None:
            logger.warning("[ApprovalFlow] set_approval_result: approval_id=%s 不存在或已处理", target_id)
            return

        event, _ = slot
        logger.info("[ApprovalFlow] set_approval_result called: approval_id=%s, result=%s", target_id, result is not None)
        self._pending[target_id] = (event, result)
        event.set()
        logger.info("[ApprovalFlow] event.set() called for approval_id=%s, waiter should wake up", target_id)

    async def wait_for_approval(self, step: LoopStep, run_id: str) -> ApprovalResult:
        """
        等待审批并返回结构化结果。

        调用方（ToolExecution handler）负责：
        1. 发送 run:waiting_for_approval 事件
        2. 根据返回的 ApprovalResult 决定状态转移
        3. 发送后续事件（tool:result / run:cancelled 等）
        """
        approval_id = step.approval_id
        if not approval_id:
            logger.error("[ApprovalFlow] wait_for_approval: step 缺少 approval_id, tool=%s", step.tool)
            return ApprovalResult(approved=False)

        event = asyncio.Event()
        self._pending[approval_id] = (event, None)

        logger.info("[ApprovalFlow] wait_for_approval: waiting, run_id=%s, tool=%s, approval_id=%s", run_id, step.tool, approval_id)
        await event.wait()
        logger.info("[ApprovalFlow] event.wait() returned for approval_id=%s, reading result", approval_id)

        _, result = self._pending.pop(approval_id, (None, None))

        if result is not None:
            logger.info("[ApprovalFlow] Approval granted: approval_id=%s, success=%s", approval_id, result.get("success", False))
            return ApprovalResult(
                approved=True,
                output=result.get("output"),
                error=result.get("error"),
                success=result.get("success", False),
                observability=result.get("observability"),
            )
        else:
            logger.info("[ApprovalFlow] Approval denied: approval_id=%s", approval_id)
            return ApprovalResult(approved=False)
