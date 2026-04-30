import { ActionReceipt } from '@/components/execution/ActionReceipt'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { ConversationMessage } from '@/types/conversation'
import { buildToolTraceDetail } from './transcriptItems'

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
}: {
  details: ActionReceiptDetail[]
  status: ActionReceiptStatus
}) {
  return (
    <ActionReceipt
      status={status}
      details={details}
    />
  )
}

export function ToolTraceCard({ message }: { message: ConversationMessage }) {
  return (
    <ToolTraceGroup
      status={toActionReceiptStatus(message)}
      details={[buildToolTraceDetail(message)]}
    />
  )
}
