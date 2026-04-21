import { useCallback, useRef, useState } from 'react'
import type { WorkspaceChatItem } from '@/types/workspace'

function createItemId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function normalizeDraftItem(item: WorkspaceChatItem): WorkspaceChatItem {
  return {
    ...item,
    isStreaming: false,
    transient: false,
  }
}

export function createExecutionDraftRoundState() {
  let sessionId: string | null = null
  let items: WorkspaceChatItem[] = []

  const clearDraftRound = () => {
    items = []
    sessionId = null
  }

  return {
    get sessionId() {
      return sessionId
    },
    get items() {
      return items
    },
    startDraftRound(nextSessionId: string, message: string) {
      sessionId = nextSessionId
      items = [{
        id: createItemId('user'),
        type: 'user-message',
        content: message,
        isStreaming: false,
        transient: false,
      }]
    },
    appendItems(nextItems: WorkspaceChatItem[]) {
      if (!sessionId || nextItems.length === 0) {
        return
      }

      items = [...items, ...nextItems.map(normalizeDraftItem)]
    },
    clearDraftRound,
  }
}

export function useExecutionDraftRound() {
  const [items, setItems] = useState<WorkspaceChatItem[]>([])
  const sessionIdRef = useRef<string | null>(null)

  const startDraftRound = useCallback((sessionId: string, message: string) => {
    sessionIdRef.current = sessionId
    setItems([{
      id: createItemId('user'),
      type: 'user-message',
      content: message,
      isStreaming: false,
      transient: false,
    }])
  }, [])

  const appendItems = useCallback((nextItems: WorkspaceChatItem[]) => {
    if (!sessionIdRef.current || nextItems.length === 0) {
      return
    }

    setItems((current) => [...current, ...nextItems.map(normalizeDraftItem)])
  }, [])

  const clearDraftRound = useCallback(() => {
    sessionIdRef.current = null
    setItems([])
  }, [])

  return {
    items,
    sessionIdRef,
    startDraftRound,
    appendItems,
    clearDraftRound,
  }
}
