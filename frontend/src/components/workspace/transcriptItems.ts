import { buildReceiptDetail } from '@/components/execution/receiptUtils'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { ConversationMessage } from '@/types/conversation'

const TOOL_GROUP_GAP_MS = 90_000

export type TranscriptItem =
  | {
      kind: 'message'
      id: string
      message: ConversationMessage
    }
  | {
      kind: 'tool_group'
      id: string
      messages: ConversationMessage[]
      details: ActionReceiptDetail[]
      status: ActionReceiptStatus
    }

function getMessageTime(message: ConversationMessage) {
  const timestamp = Date.parse(message.createdAt || message.updatedAt)
  return Number.isFinite(timestamp) ? timestamp : null
}

function isApprovalDecisionStatus(status: unknown) {
  return status === 'approved' || status === 'denied'
}

function getToolTraceStatus(message: ConversationMessage): ActionReceiptDetail['status'] {
  if (message.payloadJson.status === 'waiting_for_approval') {
    return 'waiting_for_approval'
  }
  if (message.payloadJson.status === 'approved') {
    return 'success'
  }
  if (message.payloadJson.status === 'denied') {
    return 'cancelled'
  }
  if (message.streamState === 'failed') {
    return 'failed'
  }
  if (message.streamState === 'cancelled') {
    return 'cancelled'
  }
  if (message.streamState === 'streaming' || message.streamState === 'idle') {
    return 'running'
  }
  return 'success'
}

function getToolGroupStatus(messages: ConversationMessage[]): ActionReceiptStatus {
  const failedCount = messages.filter((m) => m.streamState === 'failed').length
  if (failedCount > 0) {
    return failedCount === messages.length ? 'failed' : 'partial_failed'
  }
  if (messages.some((message) => message.streamState === 'cancelled')) {
    return 'cancelled'
  }
  if (messages.some((message) => message.payloadJson.status === 'denied')) {
    return 'cancelled'
  }
  if (messages.some((message) => message.payloadJson.status === 'waiting_for_approval')) {
    return 'waiting_for_approval'
  }
  if (messages.some((message) => (
    !isApprovalDecisionStatus(message.payloadJson.status) &&
    (message.streamState === 'streaming' || message.streamState === 'idle')
  ))) {
    return 'running'
  }
  return 'completed'
}

export function buildToolTraceDetail(message: ConversationMessage): ActionReceiptDetail {
  const payload = message.payloadJson
  const toolName = typeof payload.tool_name === 'string' ? payload.tool_name : 'tool'
  const detail = buildReceiptDetail(
    message.id,
    toolName,
    (payload.arguments as Record<string, unknown> | undefined) ?? undefined
  )

  detail.status = getToolTraceStatus(message)

  if (
    detail.status === 'waiting_for_approval' &&
    typeof message.runId === 'string' &&
    typeof payload.approval_id === 'string'
  ) {
    const approvalObj = payload.approval as Record<string, unknown> | undefined
    const approvalPayload = approvalObj?.payload as Record<string, unknown> | undefined
    const hasShellPayload = approvalPayload && typeof approvalPayload.command === 'string'

    detail.approval = {
      runId: message.runId,
      approvalId: payload.approval_id,
      ...(hasShellPayload
        ? {
            shell: {
              command: approvalPayload.command as string,
              ...(typeof approvalPayload.execution_mode === 'string'
                ? { execution_mode: approvalPayload.execution_mode }
                : {}),
              ...(Array.isArray(approvalObj?.reasons)
                ? { reasons: (approvalObj!.reasons as string[]).filter((r): r is string => typeof r === 'string') }
                : {}),
              ...(Array.isArray(approvalObj?.risks)
                ? { risks: (approvalObj!.risks as string[]).filter((r): r is string => typeof r === 'string') }
                : {}),
            },
          }
        : {}),
    }
  }

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
  } else if (typeof payload.error_message === 'string') {
    detail.error = payload.error_message
  }

  if (typeof payload.duration === 'number' && Number.isFinite(payload.duration)) {
    detail.duration = payload.duration
  }

  return detail
}

function shouldAppendToToolGroup(
  groupMessages: ConversationMessage[],
  message: ConversationMessage
) {
  const previous = groupMessages[groupMessages.length - 1]
  if (!previous) {
    return true
  }

  if (previous.turnId !== message.turnId || previous.runId !== message.runId) {
    return false
  }

  const previousTime = getMessageTime(previous)
  const nextTime = getMessageTime(message)
  if (previousTime === null || nextTime === null) {
    return true
  }

  return nextTime - previousTime <= TOOL_GROUP_GAP_MS
}

function buildToolGroup(messages: ConversationMessage[]): TranscriptItem {
  return {
    kind: 'tool_group',
    id: `tools-${messages.map((message) => message.id).join('-')}`,
    messages,
    details: messages.map(buildToolTraceDetail),
    status: getToolGroupStatus(messages),
  }
}

export function buildTranscriptItems(messages: ConversationMessage[]): TranscriptItem[] {
  const items: TranscriptItem[] = []
  let currentToolGroup: ConversationMessage[] = []

  const flushToolGroup = () => {
    if (currentToolGroup.length === 0) {
      return
    }

    items.push(buildToolGroup(currentToolGroup))
    currentToolGroup = []
  }

  messages.forEach((message) => {
    if (message.messageType !== 'tool_trace') {
      flushToolGroup()
      items.push({
        kind: 'message',
        id: message.id,
        message,
      })
      return
    }

    if (!shouldAppendToToolGroup(currentToolGroup, message)) {
      flushToolGroup()
    }

    currentToolGroup.push(message)
  })

  flushToolGroup()
  return items
}
