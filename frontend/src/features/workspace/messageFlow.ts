import type {
  ActionReceiptDetail,
  ActionReceiptStatus,
  ReceiptDetailStatus,
} from '@/components/execution/receiptUtils'
import type { WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'

export function updateFirstMatchingDetail(
  details: ActionReceiptDetail[],
  matcher: (detail: ActionReceiptDetail) => boolean,
  updater: (detail: ActionReceiptDetail) => ActionReceiptDetail
) {
  const index = details.findIndex(matcher)

  if (index === -1) {
    return details
  }

  const nextDetails = [...details]
  nextDetails[index] = updater(nextDetails[index])
  return nextDetails
}

export function finalizeReceiptItem(
  item: WorkspaceChatItem,
  forcedStatus?: ActionReceiptStatus
): WorkspaceChatItem {
  if (item.type !== 'action-receipt') {
    return item
  }

  const resolvedStatus = forcedStatus || (
    item.details?.some((detail) => detail.status === 'failed') ? 'failed' : 'completed'
  )

  return {
    ...item,
    receiptStatus: resolvedStatus,
    details: (item.details || []).map((detail) => {
      if (detail.status !== 'pending' && detail.status !== 'running') {
        return detail
      }

      const nextStatus: ReceiptDetailStatus = resolvedStatus === 'failed'
        ? 'failed'
        : resolvedStatus === 'cancelled'
          ? 'cancelled'
          : 'success'

      return { ...detail, status: nextStatus }
    })
  }
}

export function mergeRenderItems(
  persistedItems: WorkspaceChatItem[],
  overlayItems: WorkspaceChatItem[]
) {
  return [...persistedItems, ...overlayItems]
}

export function flattenRoundsToItems(rounds: WorkspaceSessionRound[]) {
  return rounds.flatMap((round) => round.items)
}

export function formatExecutionFailureMessage(result?: string | null) {
  const content = result?.trim()
  if (!content) {
    return null
  }

  return content.startsWith('错误:') ? content : `错误: ${content}`
}
