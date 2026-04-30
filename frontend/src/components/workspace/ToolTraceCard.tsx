import { ActionReceipt } from '@/components/execution/ActionReceipt'
import type { ApprovalActionPayload, ApprovalActionType } from '@/components/execution/ActionReceipt'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { ConversationMessage } from '@/types/conversation'
import { buildToolTraceDetail } from './transcriptItems'

export type ToolApprovalActionHandler = (
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) => void

function toActionReceiptStatus(message: ConversationMessage): ActionReceiptStatus {
  const status = typeof message.payloadJson.status === 'string'
    ? message.payloadJson.status
    : message.streamState

  if (status === 'failed') {
    return 'failed'
  }
  if (status === 'cancelled') {
    return 'cancelled'
  }
  if (status === 'waiting_for_approval') {
    return 'waiting_for_approval'
  }
  if (status === 'running' || status === 'streaming' || status === 'idle') {
    return 'running'
  }
  return 'completed'
}

export function ToolTraceGroup({
  details,
  status,
  onApprovalAction,
}: {
  details: ActionReceiptDetail[]
  status: ActionReceiptStatus
  onApprovalAction?: ToolApprovalActionHandler
}) {
  return (
    <ActionReceipt
      status={status}
      details={details}
      onApprovalAction={onApprovalAction}
    />
  )
}

export function ToolTraceCard({
  message,
  onApprovalAction,
}: {
  message: ConversationMessage
  onApprovalAction?: ToolApprovalActionHandler
}) {
  return (
    <ToolTraceGroup
      status={toActionReceiptStatus(message)}
      details={[buildToolTraceDetail(message)]}
      onApprovalAction={onApprovalAction}
    />
  )
}
