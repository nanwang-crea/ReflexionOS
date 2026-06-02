export type ApprovalActionType = 'approve' | 'trust' | 'deny'

export interface ApprovalActionPayload {
  runId: string
  approvalId: string
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
  onApprovalAction?.(action, {
    runId: payload.runId,
    approvalId: payload.approvalId,
  })
}
