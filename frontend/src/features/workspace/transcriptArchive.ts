import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'
import type { WorkspaceChatItem, WorkspaceSessionRound, WorkspaceChatItemType } from '@/types/workspace'
import { trimRecentRounds } from './messageFlow'

export type TranscriptArchiveItemType = Extract<
  WorkspaceChatItemType,
  'user-message' | 'assistant-message' | 'agent-update' | 'action-receipt'
>

export interface TranscriptArchiveItem {
  id: string
  itemType: TranscriptArchiveItemType
  content: string
  receiptStatus: ActionReceiptStatus | null
  detailsJson: ActionReceiptDetail[]
  sequence: number
  createdAt: string
}

function toWorkspaceItem(item: TranscriptArchiveItem): WorkspaceChatItem {
  if (item.itemType === 'action-receipt') {
    return {
      id: item.id,
      type: 'action-receipt',
      receiptStatus: item.receiptStatus || 'completed',
      details: item.detailsJson,
    }
  }

  return {
    id: item.id,
    type: item.itemType,
    content: item.content,
  }
}

export function buildRoundsFromTranscriptArchive(archive: TranscriptArchiveItem[]) {
  const rounds: WorkspaceSessionRound[] = []
  let currentRound: WorkspaceSessionRound | null = null

  archive.forEach((item) => {
    if (item.itemType === 'user-message') {
      currentRound = {
        id: `round-${item.id}`,
        createdAt: item.createdAt,
        items: [toWorkspaceItem(item)],
      }
      rounds.push(currentRound)
      return
    }

    if (!currentRound) {
      return
    }

    currentRound.items.push(toWorkspaceItem(item))
  })

  return trimRecentRounds(rounds)
}
