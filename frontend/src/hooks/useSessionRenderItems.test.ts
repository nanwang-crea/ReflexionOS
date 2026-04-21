import { describe, expect, it } from 'vitest'
import type { WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'
import { buildSessionRenderItems } from './useSessionRenderItems'

function createItem(id: string, content: string): WorkspaceChatItem {
  return {
    id,
    type: 'assistant-message',
    content,
  }
}

describe('buildSessionRenderItems', () => {
  it('derives render items from persisted rounds plus active round plus overlay items', () => {
    const persistedRounds: WorkspaceSessionRound[] = [
      {
        id: 'round-1',
        createdAt: '2026-04-21T00:00:00Z',
        items: [createItem('persisted-1', 'persisted')],
      },
    ]
    const activeRoundItems = [createItem('active-1', 'active')]
    const overlayItems = [createItem('overlay-1', 'overlay')]

    const items = buildSessionRenderItems({
      persistedRounds,
      activeRoundItems,
      overlayItems,
    })

    expect(items).toHaveLength(3)
    expect(items.map((item) => item.id)).toEqual(['persisted-1', 'active-1', 'overlay-1'])
  })
})
