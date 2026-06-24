import { ActionReceipt } from '@/components/execution/ActionReceipt'
import type { ApprovalActionPayload, ApprovalActionType } from '@/components/execution/approvalActions'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'

export type ReceiptDetailClickHandler = (detail: ActionReceiptDetail) => void
import type { ConversationMessage } from '@/types/conversation'
import { buildToolTraceDetail } from './transcriptItems'
import { DelegateToolCall } from './DelegateToolCall'

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
  onDetailClick,
}: {
  details: ActionReceiptDetail[]
  status: ActionReceiptStatus
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: ReceiptDetailClickHandler
}) {
  return (
    <ActionReceipt
      status={status}
      details={details}
      onApprovalAction={onApprovalAction}
      onDetailClick={onDetailClick}
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
  const detail = buildToolTraceDetail(message)

  // delegate 工具使用专属 UI 组件（子任务卡片）
  if (detail.toolName === 'delegate') {
    const args = typeof message.payloadJson.arguments === 'object' && message.payloadJson.arguments !== null
      ? message.payloadJson.arguments as Record<string, unknown>
      : undefined
    return <DelegateToolCall detail={detail} args={args} />
  }

  return (
    <ToolTraceGroup
      status={toActionReceiptStatus(message)}
      details={[detail]}
      onApprovalAction={onApprovalAction}
    />
  )
}
