import { buildReceiptDetail } from '@/components/execution/receiptUtils'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { ConversationMessage } from '@/types/conversation'
import { getAssistantReasoningText } from './runtimeStatus'

const TOOL_GROUP_GAP_MS = 90_000

export type TranscriptItem =
  | { kind: 'message'; id: string; message: ConversationMessage }
  | { kind: 'process_group'; id: string; runId: string; subItems: ProcessSubItem[] }
  | { kind: 'answer_message'; id: string; message: ConversationMessage }

export type ProcessSubItem =
  | { kind: 'thinking'; id: string; text: string; streamState: ConversationMessage['streamState'] }
  | { kind: 'working_note'; id: string; text: string; streamState: ConversationMessage['streamState'] }
  | { kind: 'tool_group'; id: string; messages: ConversationMessage[]; details: ActionReceiptDetail[]; status: ActionReceiptStatus }

function getMessageTime(message: ConversationMessage) {
  const timestamp = Date.parse(message.createdAt || message.updatedAt)
  return Number.isFinite(timestamp) ? timestamp : null
}

function isApprovalDecisionStatus(status: unknown) {
  return status === 'approved' || status === 'denied'
}

function getToolTraceStatus(message: ConversationMessage): ActionReceiptDetail['status'] {
  if (message.payloadJson.status === 'waiting_for_approval') return 'waiting_for_approval'
  if (message.payloadJson.status === 'approved') return 'success'
  if (message.payloadJson.status === 'denied') return 'cancelled'
  if (message.streamState === 'failed') return 'failed'
  if (message.streamState === 'cancelled') return 'cancelled'
  if (message.streamState === 'streaming' || message.streamState === 'idle') return 'running'
  return 'success'
}

function getToolGroupStatus(messages: ConversationMessage[]): ActionReceiptStatus {
  if (messages.some((m) => m.payloadJson.status === 'waiting_for_approval')) return 'waiting_for_approval'
  const failedCount = messages.filter((m) => m.streamState === 'failed').length
  if (failedCount > 0) return failedCount === messages.length ? 'failed' : 'partial_failed'
  if (messages.some((m) => m.streamState === 'cancelled')) return 'cancelled'
  if (messages.some((m) => m.payloadJson.status === 'denied')) return 'cancelled'
  if (messages.some((m) => !isApprovalDecisionStatus(m.payloadJson.status) && (m.streamState === 'streaming' || m.streamState === 'idle'))) return 'running'
  return 'completed'
}

export function buildToolTraceDetail(message: ConversationMessage): ActionReceiptDetail {
  const payload = message.payloadJson
  const toolName = typeof payload.tool_name === 'string' ? payload.tool_name : 'tool'
  const detail = buildReceiptDetail(message.id, toolName, (payload.arguments as Record<string, unknown> | undefined) ?? undefined)
  detail.status = getToolTraceStatus(message)

  if (detail.status === 'waiting_for_approval' && typeof message.runId === 'string' && typeof payload.approval_id === 'string') {
    const approvalObj = payload.approval as Record<string, unknown> | undefined
    const approvalPayload = approvalObj?.payload as Record<string, unknown> | undefined
    const hasShellPayload = approvalPayload && typeof approvalPayload.command === 'string'
    const suggestedTrust = approvalObj?.suggested_trust as Record<string, unknown> | undefined
    detail.approval = {
      runId: message.runId,
      approvalId: payload.approval_id,
      suggestedTrust: suggestedTrust ?? undefined,
      ...(hasShellPayload ? {
        shell: {
          command: approvalPayload.command as string,
          ...(typeof approvalPayload.execution_mode === 'string' ? { execution_mode: approvalPayload.execution_mode } : {}),
          ...(Array.isArray(approvalObj?.reasons) ? { reasons: (approvalObj!.reasons as string[]).filter((r): r is string => typeof r === 'string') } : {}),
          ...(Array.isArray(approvalObj?.risks) ? { risks: (approvalObj!.risks as string[]).filter((r): r is string => typeof r === 'string') } : {}),
        },
      } : {}),
    }
  }

  if (typeof payload.output === 'string') { detail.output = payload.output }
  else if (payload.output !== undefined) { try { detail.output = JSON.stringify(payload.output, null, 2) } catch { detail.output = String(payload.output) } }

  if (typeof payload.error === 'string') { detail.error = payload.error }
  else if (typeof payload.error_message === 'string') { detail.error = payload.error_message }

  if (typeof payload.duration === 'number' && Number.isFinite(payload.duration)) { detail.duration = payload.duration }

  return detail
}

function shouldAppendToToolGroup(groupMessages: ConversationMessage[], message: ConversationMessage) {
  const previous = groupMessages[groupMessages.length - 1]
  if (!previous) return true
  if (previous.turnId !== message.turnId || previous.runId !== message.runId) return false
  const previousTime = getMessageTime(previous)
  const nextTime = getMessageTime(message)
  if (previousTime === null || nextTime === null) return true
  return nextTime - previousTime <= TOOL_GROUP_GAP_MS
}

export function isProcessGroupStreaming(subItems: ProcessSubItem[]): boolean {
  return subItems.some((item) => {
    if (item.kind === 'thinking' || item.kind === 'working_note') {
      return item.streamState === 'streaming' || item.streamState === 'idle'
    }
    if (item.kind === 'tool_group') {
      return item.status === 'running' || item.status === 'waiting_for_approval'
    }
    return false
  })
}

export function buildTranscriptItems(messages: ConversationMessage[]): TranscriptItem[] {
  const items: TranscriptItem[] = []

  let currentRunId: string | null = null
  let currentSubItems: ProcessSubItem[] = []
  let currentToolBuffer: ConversationMessage[] = []

  const flushToolBuffer = () => {
    if (currentToolBuffer.length === 0) return
    currentSubItems.push({
      kind: 'tool_group',
      id: `tools-${currentToolBuffer[0].id}`,
      messages: currentToolBuffer,
      details: currentToolBuffer.map(buildToolTraceDetail),
      status: getToolGroupStatus(currentToolBuffer),
    })
    currentToolBuffer = []
  }

  const flushProcessGroup = () => {
    flushToolBuffer()
    if (currentRunId !== null && currentSubItems.length > 0) {
      items.push({
        kind: 'process_group',
        id: `process-${currentRunId}`,
        runId: currentRunId,
        subItems: currentSubItems,
      })
    }
    currentRunId = null
    currentSubItems = []
  }

  for (const message of messages) {
    if (message.messageType === 'user_message' || message.messageType === 'system_notice') {
      flushProcessGroup()
      items.push({ kind: 'message', id: message.id, message })
      continue
    }

    if (message.messageType === 'tool_trace') {
      const runId = message.runId ?? 'unknown'
      if (currentRunId !== null && currentRunId !== runId) {
        flushProcessGroup()
      }
      if (currentRunId === null) {
        currentRunId = runId
        currentSubItems = []
        currentToolBuffer = []
      }
      if (!shouldAppendToToolGroup(currentToolBuffer, message)) {
        flushToolBuffer()
      }
      currentToolBuffer.push(message)
      continue
    }

    if (message.messageType === 'assistant_message') {
      const runId = message.runId ?? 'unknown'
      const isWorkingNote = message.displayMode === 'working_note'
      const reasoningText = getAssistantReasoningText(message)

      if (isWorkingNote) {
        if (currentRunId !== null && currentRunId !== runId) {
          flushProcessGroup()
        }
        if (currentRunId === null) {
          currentRunId = runId
          currentSubItems = []
          currentToolBuffer = []
        }
        flushToolBuffer()
        if (message.contentText) {
          currentSubItems.push({
            kind: 'working_note',
            id: message.id,
            text: message.contentText,
            streamState: message.streamState,
          })
        }
        continue
      }

      if (reasoningText) {
        if (currentRunId !== null && currentRunId !== runId) {
          flushProcessGroup()
        }
        if (currentRunId === null) {
          currentRunId = runId
          currentSubItems = []
          currentToolBuffer = []
        }
        flushToolBuffer()
        currentSubItems.push({
          kind: 'thinking',
          id: `thinking-${message.id}`,
          text: reasoningText,
          streamState: message.streamState,
        })
      }

      if (message.contentText) {
        flushProcessGroup()
        items.push({ kind: 'answer_message', id: message.id, message })
      }

      continue
    }
  }

  flushProcessGroup()
  return items
}
