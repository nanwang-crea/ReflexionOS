import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'

export type WorkspaceChatItemType =
  | 'user-message'
  | 'assistant-status'
  | 'assistant-message'
  | 'agent-update'
  | 'action-receipt'

export interface WorkspaceChatItem {
  id: string
  type: WorkspaceChatItemType
  content?: string
  statusLabel?: string
  receiptStatus?: ActionReceiptStatus
  details?: ActionReceiptDetail[]
  isStreaming?: boolean
  transient?: boolean
}

export interface WorkspaceSessionRound {
  id: string
  createdAt: string
  items: WorkspaceChatItem[]
}

export interface SessionHistoryItem {
  id: string
  type: Extract<WorkspaceChatItemType, 'user-message' | 'assistant-message' | 'agent-update' | 'action-receipt'>
  content: string
  receiptStatus?: ActionReceiptStatus
  details: ActionReceiptDetail[]
  createdAt: string
}

export interface SessionHistory {
  sessionId: string
  projectId: string | null
  rounds: Array<{
    id: string
    createdAt: string
    items: SessionHistoryItem[]
  }>
}

export interface SessionSummary {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  createdAt: string
  updatedAt: string
}

export interface SessionCreatePayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

export interface SessionUpdatePayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}
