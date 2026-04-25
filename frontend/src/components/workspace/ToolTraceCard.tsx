import { ActionReceipt } from '@/components/execution/ActionReceipt'
import { buildReceiptDetail } from '@/components/execution/receiptUtils'
import type { ConversationMessage } from '@/types/conversation'

function toActionReceiptStatus(message: ConversationMessage): 'running' | 'completed' | 'failed' | 'cancelled' {
  const status = typeof message.payloadJson.status === 'string'
    ? message.payloadJson.status
    : message.streamState

  if (status === 'failed') {
    return 'failed'
  }
  if (status === 'cancelled') {
    return 'cancelled'
  }
  if (status === 'running' || status === 'streaming' || status === 'idle') {
    return 'running'
  }
  return 'completed'
}

export function ToolTraceCard({ message }: { message: ConversationMessage }) {
  const payload = message.payloadJson
  const toolName = typeof payload.tool_name === 'string' ? payload.tool_name : 'tool'
  const detail = buildReceiptDetail(
    message.id,
    toolName,
    (payload.arguments as Record<string, unknown> | undefined) ?? undefined
  )

  detail.status = (
    message.streamState === 'failed'
      ? 'failed'
      : message.streamState === 'cancelled'
        ? 'cancelled'
        : message.streamState === 'streaming' || message.streamState === 'idle'
          ? 'running'
          : 'success'
  )

  if (typeof payload.output === 'string') {
    detail.output = payload.output
  } else if (payload.output !== undefined) {
    try {
      detail.output = JSON.stringify(payload.output, null, 2)
    } catch (_error) {
      detail.output = String(payload.output)
    }
  }

  if (typeof payload.error === 'string') {
    detail.error = payload.error
  }

  if (typeof payload.duration === 'number' && Number.isFinite(payload.duration)) {
    detail.duration = payload.duration
  }

  return (
    <ActionReceipt
      status={toActionReceiptStatus(message)}
      details={[detail]}
    />
  )
}
