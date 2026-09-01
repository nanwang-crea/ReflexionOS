/**
 * 文件功能：审批操作类型定义与派发
 * 文件描述：定义命令执行审批（批准/信任/拒绝）相关的类型，以及将审批操作转发给外部处理函数的工具方法
 * 核心逻辑：ActionReceipt 等组件在用户点击审批按钮时调用 sendApprovalAction，统一组装 payload 后转发给外部传入的 onApprovalAction 回调
 */
export type ApprovalActionType = 'approve' | 'trust' | 'deny'

export interface ApprovalActionPayload {
  runId: string
  approvalId: string
  parentSessionId?: string  // SubAgent 的父 session ID，用于路由审批响应
}

export type ApprovalActionHandler = (
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) => void

/**
 * 函数名：sendApprovalAction
 * 入参：
 *   - onApprovalAction (ApprovalActionHandler | undefined): 外部传入的审批处理回调，可能未提供
 *   - action (ApprovalActionType): 用户选择的审批动作（approve/trust/deny）
 *   - payload (ApprovalActionPayload): 审批相关的上下文数据（runId、approvalId、父 session ID）
 * 功能：将审批动作转发给外部回调，统一 payload 结构
 * 运行逻辑：
 *   1. 若未提供回调则直接返回，不做任何处理
 *   2. 否则重新组装 payload（避免直接传递引用）并调用回调
 * 出参：无（void），仅触发副作用调用
 */
export function sendApprovalAction(
  onApprovalAction: ApprovalActionHandler | undefined,
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) {
  if (!onApprovalAction) {
    return
  }

  onApprovalAction(action, {
    runId: payload.runId,
    approvalId: payload.approvalId,
    parentSessionId: payload.parentSessionId,
  })
}
