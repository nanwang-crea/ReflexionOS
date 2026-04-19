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

export interface ChatSession {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  items: WorkspaceChatItem[]
  createdAt: string
  updatedAt: string
}
