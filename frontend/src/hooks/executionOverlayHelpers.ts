import type { WorkspaceChatItem } from '@/types/workspace'
import { createOverlayRuntimeState, type OverlayRuntimeState } from './executionOverlayState'

export function createOverlayItemId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function createStatusOverlayItem(statusLabel: string): WorkspaceChatItem {
  return {
    id: createOverlayItemId('status'),
    type: 'assistant-status',
    statusLabel,
    transient: true,
  }
}

export function createReceiptOverlayItem(): WorkspaceChatItem {
  return {
    id: createOverlayItemId('receipt'),
    type: 'action-receipt',
    receiptStatus: 'running',
    details: [],
    transient: true,
  }
}

export function createAssistantMessageItem(content: string): WorkspaceChatItem {
  return {
    id: createOverlayItemId('assistant'),
    type: 'assistant-message',
    content,
  }
}

export function createExecutionRunState(sessionId: string): {
  statusItem: WorkspaceChatItem
  runtimeState: OverlayRuntimeState
} {
  const statusItem = createStatusOverlayItem('正在思考中')
  const runtimeState = createOverlayRuntimeState()

  return {
    statusItem,
    runtimeState: {
      ...runtimeState,
      currentStatusItemId: statusItem.id,
      activeSessionId: sessionId,
    },
  }
}
