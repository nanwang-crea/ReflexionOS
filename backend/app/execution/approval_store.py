"""
待批准工具调用的内存存储（PendingApprovalStore）。

维护"待审批 -> 已批准/已拒绝/已过期"的状态机，供审批流程（ApprovalFlow）
和路由层查询/变更审批状态。使用 RLock 保证多线程环境下的并发安全，
所有对外返回的 PendingToolApproval 均为深拷贝，避免调用方修改内部状态。
"""

from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Literal

from app.models.approval import (
    AllowApprovalDecision,
    ApprovalDecision,
    PendingToolApproval,
)


class PendingApprovalStore:
    """
    待审批工具调用的存储与状态转移。

    每条审批记录的状态机：pending -> approved / denied / expired。
    内部用 dict 以 approval_id 为键保存 PendingToolApproval，配合 RLock
    保证并发读写安全。
    """

    def __init__(self) -> None:
        """初始化空的审批存储：内部字典 `_approvals` 和用于并发保护的 `_lock`。"""
        self._approvals: dict[str, PendingToolApproval] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        approval_id: str | None = None,
        session_id: str,
        turn_id: str,
        run_id: str,
        step_number: int,
        tool_call_id: str,
        tool_name: str,
        tool_arguments: dict,
        approval_payload: dict,
    ) -> PendingToolApproval:
        """
        创建一条新的待审批记录（初始状态为 pending）。

        参数：
            approval_id：审批记录 ID，为 None 时由 PendingToolApproval 自动生成；
                显式传入且已存在时抛出 ValueError。
            session_id/turn_id/run_id：所属会话/对话轮次/执行运行的 ID。
            step_number：该工具调用在执行流程中的步骤序号。
            tool_call_id/tool_name/tool_arguments：待审批的工具调用信息
                （tool_arguments 会深拷贝，避免外部后续修改影响存储内容）。
            approval_payload：审批展示所需的附加信息（深拷贝存储）。
        工作流程：加锁后组装字段字典，若指定了 approval_id 则校验唯一性，
        构造 PendingToolApproval 实例并存入内部字典。
        返回值：新创建记录的深拷贝（PendingToolApproval）。
        """
        with self._lock:
            pending_data = {
                "session_id": session_id,
                "turn_id": turn_id,
                "run_id": run_id,
                "step_number": step_number,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "tool_arguments": deepcopy(tool_arguments),
                "approval_payload": deepcopy(approval_payload),
            }
            if approval_id is not None:
                if approval_id in self._approvals:
                    raise ValueError(f"approval already exists: {approval_id}")
                pending_data["id"] = approval_id
            pending = PendingToolApproval(**pending_data)
            self._approvals[pending.id] = pending
            return pending.model_copy(deep=True)

    def get(self, approval_id: str) -> PendingToolApproval | None:
        """
        按 ID 查询审批记录。

        参数：approval_id：审批记录 ID。
        返回值：存在则返回该记录的深拷贝；不存在返回 None。
        """
        with self._lock:
            pending = self._approvals.get(approval_id)
            if pending is None:
                return None
            return pending.model_copy(deep=True)

    def approve(
        self, approval_id: str, *, decision: AllowApprovalDecision = "allow_once"
    ) -> PendingToolApproval:
        """
        批准一条待审批记录，状态转为 approved。

        参数：
            approval_id：审批记录 ID。
            decision：批准类型（如 allow_once/allow_always 等），不允许传 "deny"
                （会抛出 ValueError，拒绝请走 `deny` 方法）。
        返回值：更新后记录的深拷贝。若记录不存在抛 KeyError，若记录已非
        pending 状态抛 ValueError（见 `_decide`）。
        """
        if decision == "deny":
            raise ValueError("approve decision cannot be deny")
        return self._decide(approval_id, status="approved", decision=decision)

    def deny(self, approval_id: str) -> PendingToolApproval:
        """
        拒绝一条待审批记录，状态转为 denied。

        参数：approval_id：审批记录 ID。
        返回值：更新后记录的深拷贝。若记录不存在抛 KeyError，若记录已非
        pending 状态抛 ValueError（见 `_decide`）。
        """
        return self._decide(approval_id, status="denied", decision="deny")

    def list_pending_approval_ids_for_session(self, session_id: str) -> list[str]:
        """
        列出指定会话下所有仍处于 pending 状态的审批 ID。

        参数：session_id：会话 ID。
        返回值：符合条件的 approval_id 列表（不保证顺序）。
        """
        with self._lock:
            return [
                aid
                for aid, pending in self._approvals.items()
                if pending.session_id == session_id and pending.status == "pending"
            ]

    def expire_for_run(self, run_id: str) -> list[PendingToolApproval]:
        """
        将指定运行下所有 pending 状态的审批记录标记为 expired。

        参数：run_id：执行运行 ID（通常在该 run 被取消/结束时调用，清理遗留的
            待审批项，避免其永久挂起）。
        工作流程：遍历所有记录，筛选出属于该 run_id 且状态为 pending 的记录，
        更新状态为 expired 并记录 decided_at 时间戳。
        返回值：本次被标记为 expired 的记录列表（深拷贝）。
        """
        expired: list[PendingToolApproval] = []
        with self._lock:
            for approval_id, pending in list(self._approvals.items()):
                if pending.run_id != run_id or pending.status != "pending":
                    continue
                updated = pending.model_copy(
                    update={"status": "expired", "decided_at": datetime.now()}
                )
                self._approvals[approval_id] = updated
                expired.append(updated.model_copy(deep=True))
        return expired

    def expire_for_session(self, session_id: str) -> list[PendingToolApproval]:
        """
        将指定会话下所有 pending 状态的审批记录标记为 expired。

        参数：session_id：会话 ID（通常在会话结束/清理时调用）。
        工作流程：与 `expire_for_run` 相同，仅过滤条件换成 session_id。
        返回值：本次被标记为 expired 的记录列表（深拷贝）。
        """
        expired: list[PendingToolApproval] = []
        with self._lock:
            for approval_id, pending in list(self._approvals.items()):
                if pending.session_id != session_id or pending.status != "pending":
                    continue
                updated = pending.model_copy(
                    update={"status": "expired", "decided_at": datetime.now()}
                )
                self._approvals[approval_id] = updated
                expired.append(updated.model_copy(deep=True))
        return expired

    def _decide(
        self,
        approval_id: str,
        *,
        status: Literal["approved", "denied"],
        decision: ApprovalDecision,
    ) -> PendingToolApproval:
        """
        内部通用方法：将指定审批记录从 pending 转为 approved/denied。

        参数：
            approval_id：审批记录 ID。
            status：目标状态（approved 或 denied）。
            decision：具体决定类型（如 allow_once/allow_always/deny）。
        工作流程：加锁查找记录；不存在抛 KeyError；非 pending 状态抛
        ValueError（防止重复决定）；否则更新 status/decision/decided_at
        三个字段并写回存储。
        返回值：更新后记录的深拷贝。
        """
        with self._lock:
            pending = self._approvals.get(approval_id)
            if pending is None:
                raise KeyError(f"approval not found: {approval_id}")
            if pending.status != "pending":
                raise ValueError(f"approval is not pending: {approval_id}")
            updated = pending.model_copy(
                update={
                    "status": status,
                    "decision": decision,
                    "decided_at": datetime.now(),
                }
            )
            self._approvals[approval_id] = updated
            return updated.model_copy(deep=True)
