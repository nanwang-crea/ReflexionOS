import { useCallback, useRef, useState } from 'react'
import type { WorkspaceChatItem } from '@/types/workspace'

export function useExecutionOverlayUi() {
  const [overlayItems, setOverlayItems] = useState<WorkspaceChatItem[]>([])
  const overlayItemsRef = useRef<WorkspaceChatItem[]>([])

  const setOverlayState = useCallback((
    updater: WorkspaceChatItem[] | ((items: WorkspaceChatItem[]) => WorkspaceChatItem[])
  ) => {
    setOverlayItems((current) => {
      const nextItems = typeof updater === 'function'
        ? updater(current)
        : updater
      overlayItemsRef.current = nextItems
      return nextItems
    })
  }, [])

  const addOverlayItem = useCallback((item: WorkspaceChatItem) => {
    setOverlayState((items) => [...items, item])
  }, [setOverlayState])

  const updateOverlayItem = useCallback((
    itemId: string,
    updater: (item: WorkspaceChatItem) => WorkspaceChatItem
  ) => {
    setOverlayState((items) => items.map((item) => (
      item.id === itemId
        ? updater(item)
        : item
    )))
  }, [setOverlayState])

  const removeOverlayItem = useCallback((itemId: string) => {
    setOverlayState((items) => items.filter((item) => item.id !== itemId))
  }, [setOverlayState])

  const getOverlayItem = useCallback((itemId: string) => (
    overlayItemsRef.current.find((item) => item.id === itemId) || null
  ), [])

  const clearOverlayItems = useCallback(() => {
    setOverlayState([])
  }, [setOverlayState])

  return {
    overlayItems,
    setOverlayState,
    addOverlayItem,
    updateOverlayItem,
    removeOverlayItem,
    getOverlayItem,
    clearOverlayItems,
  }
}
