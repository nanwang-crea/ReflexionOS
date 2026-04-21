import { useEffect, useMemo, useRef } from 'react'
import { flattenRoundsToItems, mergeRenderItems } from '@/features/workspace/messageFlow'
import type { WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'

interface UseSessionRenderItemsOptions {
  persistedRounds: WorkspaceSessionRound[]
  activeRoundItems: WorkspaceSessionRound['items']
  overlayItems: WorkspaceChatItem[]
}

export function buildSessionRenderItems(options: UseSessionRenderItemsOptions) {
  return mergeRenderItems(
    [...flattenRoundsToItems(options.persistedRounds), ...options.activeRoundItems],
    options.overlayItems
  )
}

export function useSessionRenderItems(options: UseSessionRenderItemsOptions) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { persistedRounds, activeRoundItems, overlayItems } = options
  const renderItems = useMemo(
    () => buildSessionRenderItems({ persistedRounds, activeRoundItems, overlayItems }),
    [persistedRounds, activeRoundItems, overlayItems]
  )

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [renderItems])

  return {
    messagesEndRef,
    renderItems,
  }
}
