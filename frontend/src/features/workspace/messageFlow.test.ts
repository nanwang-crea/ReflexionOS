import { describe, expect, it } from 'vitest'
import type { WorkspaceChatItem } from '@/types/workspace'
import {
  deriveSessionTitle,
  finalizeReceiptItem,
  mergeRenderItems,
} from './messageFlow'

describe('deriveSessionTitle', () => {
  it('uses the first user message and truncates long content', () => {
    const items: WorkspaceChatItem[] = [
      {
        id: 'assistant-1',
        type: 'assistant-message',
        content: 'hello',
      },
      {
        id: 'user-1',
        type: 'user-message',
        content: 'This is a very long message that should be truncated for the title',
      },
    ]

    expect(deriveSessionTitle(items)).toBe('This is a very long message...')
  })
})

describe('finalizeReceiptItem', () => {
  it('marks pending and running details as successful when the receipt completes', () => {
    const nextItem = finalizeReceiptItem({
      id: 'receipt-1',
      type: 'action-receipt',
      receiptStatus: 'running',
      details: [
        {
          id: 'detail-1',
          toolName: 'shell',
          summary: 'Run shell command',
          category: 'command',
          status: 'running',
        },
        {
          id: 'detail-2',
          toolName: 'file',
          summary: 'Read file',
          category: 'explore',
          status: 'success',
        },
      ],
    })

    expect(nextItem.receiptStatus).toBe('completed')
    expect(nextItem.details?.map((detail) => detail.status)).toEqual(['success', 'success'])
  })
})

describe('mergeRenderItems', () => {
  it('renders persisted items first and transient overlay items after them', () => {
    const persistedItems: WorkspaceChatItem[] = [
      {
        id: 'user-1',
        type: 'user-message',
        content: 'hello',
      },
    ]
    const overlayItems: WorkspaceChatItem[] = [
      {
        id: 'status-1',
        type: 'assistant-status',
        statusLabel: '正在思考中',
        transient: true,
      },
    ]

    expect(mergeRenderItems(persistedItems, overlayItems).map((item) => item.id)).toEqual([
      'user-1',
      'status-1',
    ])
  })
})
