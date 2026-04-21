import { describe, expect, it } from 'vitest'
import type { SessionHistory } from '@/types/workspace'
import { normalizeRoundFromApi } from './sessionHistoryRound'

const receiptDetail = {
  id: 'detail-1',
  toolName: 'shell',
  status: 'failed' as const,
  summary: 'Shell command failed',
  category: 'command' as const,
  error: 'boom',
}

describe('normalizeRoundFromApi', () => {
  it('preserves explicit receiptStatus values like failed', () => {
    const round: SessionHistory['rounds'][number] = {
      id: 'round-1',
      createdAt: '2026-04-20T00:00:00Z',
      items: [
        {
          id: 'receipt-1',
          type: 'action-receipt',
          content: '',
          receiptStatus: 'failed',
          details: [receiptDetail],
          createdAt: '2026-04-20T00:00:01Z',
        },
      ],
    }

    expect(normalizeRoundFromApi(round)).toEqual({
      id: 'round-1',
      createdAt: '2026-04-20T00:00:00Z',
      items: [
        {
          id: 'receipt-1',
          type: 'action-receipt',
          receiptStatus: 'failed',
          details: [receiptDetail],
        },
      ],
    })
  })

  it('maps persisted non-receipt items such as agent-update', () => {
    const round: SessionHistory['rounds'][number] = {
      id: 'round-2',
      createdAt: '2026-04-20T00:02:00Z',
      items: [
        {
          id: 'item-1',
          type: 'agent-update',
          content: 'Running tools',
          details: [],
          createdAt: '2026-04-20T00:02:01Z',
        },
      ],
    }

    expect(normalizeRoundFromApi(round)).toEqual({
      id: 'round-2',
      createdAt: '2026-04-20T00:02:00Z',
      items: [
        {
          id: 'item-1',
          type: 'agent-update',
          content: 'Running tools',
        },
      ],
    })
  })
})
