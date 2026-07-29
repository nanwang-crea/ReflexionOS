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

export function sendApprovalAction(
  onApprovalAction: ApprovalActionHandler | undefined,
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) {
  if (!onApprovalAction) {
    console.warn('[SubAgent Approval] 警告: onApprovalAction 回调未定义')
    return
  }
  
  onApprovalAction(action, {
    runId: payload.runId,
    approvalId: payload.approvalId,
    parentSessionId: payload.parentSessionId,
  })
}
