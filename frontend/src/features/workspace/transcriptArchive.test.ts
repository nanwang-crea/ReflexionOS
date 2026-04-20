import { describe, expect, it } from 'vitest'
import type { TranscriptArchiveItem } from './transcriptArchive'
import { buildRoundsFromTranscriptArchive } from './transcriptArchive'

describe('buildRoundsFromTranscriptArchive', () => {
  it('replays agent updates and receipts inside the same round', () => {
    const archive: TranscriptArchiveItem[] = [
      { id: '1', itemType: 'user-message', content: 'hello', receiptStatus: null, detailsJson: [], sequence: 0, createdAt: '1' },
      { id: '2', itemType: 'agent-update', content: 'checking files', receiptStatus: null, detailsJson: [], sequence: 1, createdAt: '2' },
      {
        id: '3',
        itemType: 'action-receipt',
        content: '',
        receiptStatus: 'completed',
        detailsJson: [{ id: 'detail-1', status: 'success', summary: '执行 file', toolName: 'file', category: 'other' }],
        sequence: 2,
        createdAt: '3',
      },
      { id: '4', itemType: 'assistant-message', content: 'done', receiptStatus: null, detailsJson: [], sequence: 3, createdAt: '4' },
    ]

    const rounds = buildRoundsFromTranscriptArchive(archive)

    expect(rounds).toHaveLength(1)
    expect(rounds[0].items.map((item) => item.type)).toEqual([
      'user-message',
      'agent-update',
      'action-receipt',
      'assistant-message',
    ])
  })
})
