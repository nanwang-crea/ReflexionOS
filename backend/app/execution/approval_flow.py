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


class ApprovalFlow:
    """
    审批流 — 只负责等待/接收审批结果，返回结构化 ApprovalResult。
    不负责：tool 执行、状态转移、事件发送。
    """

    def __init__(self, emit: Callable[[str, dict], Awaitable[None]]):
        self._emit = emit
        self._resume_event: asyncio.Event = asyncio.Event()
        self._pending_result: dict | None = None

    def set_approval_result(self, result: dict | None) -> None:
        """外部调用：审批结果写入"""
        logger.info("[ApprovalFlow] set_approval_result called: result=%s, _resume_event.is_set()=%s", result is not None, self._resume_event.is_set())
        self._pending_result = result
        self._resume_event.set()
        logger.info("[ApprovalFlow] _resume_event.set() called, waiters should wake up")

    async def wait_for_approval(self, step: LoopStep, run_id: str) -> ApprovalResult:
        """
        等待审批并返回结构化结果。

        调用方（ToolExecution handler）负责：
        1. 发送 run:waiting_for_approval 事件
        2. 根据返回的 ApprovalResult 决定状态转移
        3. 发送后续事件（tool:result / run:cancelled 等）
        """
        logger.info("[ApprovalFlow] wait_for_approval: waiting for _resume_event, run_id=%s, tool=%s", run_id, step.tool)
        await self._resume_event.wait()
        logger.info("[ApprovalFlow] _resume_event.wait() returned, reading _pending_result")
        result = self._pending_result
        self._pending_result = None
        self._resume_event = asyncio.Event()

        if result is not None:
            logger.info("[ApprovalFlow] Approval granted: success=%s", result.get("success", False))
            return ApprovalResult(
                approved=True,
                output=result.get("output"),
                error=result.get("error"),
                success=result.get("success", False),
            )
        else:
            logger.info("[ApprovalFlow] Approval denied")
            return ApprovalResult(approved=False)
