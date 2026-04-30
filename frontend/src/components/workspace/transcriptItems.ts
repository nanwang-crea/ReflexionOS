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

function getToolTraceStatus(message: ConversationMessage): ActionReceiptDetail['status'] {
  if (message.payloadJson.status === 'waiting_for_approval') {
    return 'waiting_for_approval'
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
  if (messages.some((message) => message.streamState === 'failed')) {
    return 'failed'
  }
  if (messages.some((message) => message.streamState === 'cancelled')) {
    return 'cancelled'
  }
  if (messages.some((message) => message.payloadJson.status === 'waiting_for_approval')) {
    return 'waiting_for_approval'
  }
  if (messages.some((message) => message.streamState === 'streaming' || message.streamState === 'idle')) {
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
