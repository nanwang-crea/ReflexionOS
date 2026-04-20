import { describe, expect, it } from 'vitest'
import type { WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'
import {
  deriveSessionTitle,
  flattenRoundsToItems,
  finalizeReceiptItem,
  formatExecutionFailureMessage,
  mergeRenderItems,
  trimRecentRounds,
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

  it('keeps current round items visible while overlay receipts are also rendering', () => {
    const persistedItems: WorkspaceChatItem[] = [
      {
        id: 'user-1',
        type: 'user-message',
        content: 'hello',
      },
      {
        id: 'update-1',
        type: 'agent-update',
        content: '已探索 1 个文件',
      },
    ]
    const overlayItems: WorkspaceChatItem[] = [
      {
        id: 'receipt-1',
        type: 'action-receipt',
        receiptStatus: 'running',
        details: [],
        transient: true,
      },
    ]

    expect(mergeRenderItems(persistedItems, overlayItems).map((item) => item.id)).toEqual([
      'user-1',
      'update-1',
      'receipt-1',
    ])
  })
})

describe('trimRecentRounds', () => {
  it('keeps only the latest 10 rounds', () => {
    const rounds: WorkspaceSessionRound[] = Array.from({ length: 12 }, (_, index) => ({
      id: `round-${index + 1}`,
      createdAt: `${index + 1}`,
      items: [],
    }))

    expect(trimRecentRounds(rounds)).toHaveLength(10)
    expect(trimRecentRounds(rounds)[0].id).toBe('round-3')
  })
})

describe('flattenRoundsToItems', () => {
  it('returns render items in round order', () => {
    const rounds: WorkspaceSessionRound[] = [
      {
        id: 'round-1',
        createdAt: '1',
        items: [{ id: 'user-1', type: 'user-message', content: 'hello' }],
      },
    ]

    expect(flattenRoundsToItems(rounds).map((item) => item.id)).toEqual(['user-1'])
  })
})

describe('formatExecutionFailureMessage', () => {
  it('prefers the backend result when a failed completion is received without an execution:error event', () => {
    expect(formatExecutionFailureMessage('执行异常: 工具调用失败')).toBe('错误: 执行异常: 工具调用失败')
  })

  it('returns null when there is no stable failure detail to show', () => {
    expect(formatExecutionFailureMessage('')).toBe(null)
    expect(formatExecutionFailureMessage(undefined)).toBe(null)
  })
})
