import type { SessionHistory, WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'

export type SessionHistoryRoundFromApi = SessionHistory['rounds'][number]

function normalizeItemFromApi(item: SessionHistoryRoundFromApi['items'][number]): WorkspaceChatItem {
  if (item.type === 'action-receipt') {
    return {
      id: item.id,
      type: 'action-receipt',
      receiptStatus: item.receiptStatus || 'completed',
      details: item.details,
    }
  }

  return {
    id: item.id,
    type: item.type,
    content: item.content,
  }
}

export function normalizeRoundFromApi(round: SessionHistoryRoundFromApi): WorkspaceSessionRound {
  return {
    id: round.id,
    createdAt: round.createdAt,
    items: round.items.map((item) => normalizeItemFromApi(item)),
  }
}
