# 工具调用审批相关的数据模型：定义待审批工具调用的状态、用户决策类型，
# 以及待审批记录本身的结构（用于 Agent 执行过程中需要人工确认的工具调用）。
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.ids import new_approval_id as _new_approval_id

# 审批状态：待处理/已批准/已拒绝/已过期/已过时（陈旧，通常因 run 已结束而失效）
ApprovalStatus = Literal["pending", "approved", "denied", "expired", "stale"]
# 用户对审批的决策：仅本次允许/拒绝/信任并允许（后续同类工具调用自动放行）
ApprovalDecision = Literal["allow_once", "deny", "trust_and_allow"]
# 表示“允许”类决策的子集（不含 deny），用于需要限定为放行场景的类型标注
AllowApprovalDecision = Literal["allow_once", "trust_and_allow"]


class PendingToolApproval(BaseModel):
    """待审批的工具调用记录：Agent 在执行过程中触发需要人工确认的工具调用时创建，
    记录该调用所属的会话/回合/运行、具体的工具名与参数，以及审批状态与决策结果。"""

    id: str = Field(default_factory=_new_approval_id)
    session_id: str
    turn_id: str
    run_id: str
    step_number: int  # 该工具调用在所属 run 中的执行步骤序号
    tool_call_id: str
    tool_name: str
    tool_arguments: dict
    approval_payload: dict  # 展示给用户用于审批判断的附加信息（如风险提示、影响范围等）
    status: ApprovalStatus = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    decided_at: datetime | None = None
    decision: ApprovalDecision | None = None
