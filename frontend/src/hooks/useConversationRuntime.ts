import { useCallback, useEffect, useRef, useState } from 'react'
import { conversationApi } from '@/features/conversation/conversationApi'
import { useConversationStore } from '@/features/conversation/conversationStore'
import type { ConnectionStatus } from '@/features/workspace/types'
import type { LlmRetryDto, PlanDto } from '@/services/sessionConversationWebSocket'
import {
  SessionConversationWebSocket,
  type SessionConversationEventDto,
  type SessionConversationLiveMessageDto,
} from '@/services/sessionConversationWebSocket'
import type { ConversationEvent, ConversationLiveMessage, ConversationState } from '@/types/conversation'

interface StartTurnPayload {
  sessionId: string
  message: string
  providerId?: string | null
  modelId?: string | null
}

const INCREMENTAL_EVENT_TYPES = new Set([
  'message.payload_updated',
])

export function createSnapshotRefreshQueue(
  refreshSnapshot: (sessionId: string) => Promise<void>
) {
  const queuedSessionIds: string[] = []
  const queuedSessionSet = new Set<string>()
  let refreshInFlight = false

  const drainQueue = async () => {
    if (refreshInFlight) {
      return
    }

    refreshInFlight = true
    try {
      while (queuedSessionIds.length > 0) {
        const sessionId = queuedSessionIds.shift()
        if (!sessionId) {
          continue
        }

        queuedSessionSet.delete(sessionId)
        try {
          await refreshSnapshot(sessionId)
        } catch (error) {
          console.error('Failed to refresh conversation snapshot:', error)
        }
      }
    } finally {
      refreshInFlight = false
    }
  }

  return (sessionId: string) => {
    if (!queuedSessionSet.has(sessionId)) {
      queuedSessionSet.add(sessionId)
      queuedSessionIds.push(sessionId)
    }

    void drainQueue()
  }
}

function toConversationEvent(event: SessionConversationEventDto): ConversationEvent {
  return {
    id: event.id,
    sessionId: event.session_id,
    seq: event.seq,
    turnId: event.turn_id,
    runId: event.run_id,
    messageId: event.message_id,
    eventType: event.event_type,
    payloadJson: event.payload_json,
    createdAt: event.created_at,
  }
}

function toConversationLiveMessage(message: SessionConversationLiveMessageDto): ConversationLiveMessage {
  return {
    sessionId: message.session_id,
    turnId: message.turn_id,
    runId: message.run_id,
    messageId: message.message_id,
    messageType: message.message_type as ConversationLiveMessage['messageType'],
    contentText: message.content_text,
    streamState: message.stream_state as ConversationLiveMessage['streamState'],
    delta: message.delta,
  }
}

function resolveActiveRunId(conversation: ConversationState | undefined): string | null {
  if (!conversation) {
    return null
  }

  const activeTurnId = conversation.session?.activeTurnId
  if (activeTurnId) {
    const activeRunId = conversation.turnsById[activeTurnId]?.activeRunId
    if (activeRunId) {
      return activeRunId
    }
  }

  const running = Object.values(conversation.runsById).find((run) => run.status === 'running' || run.status === 'created')
  return running?.id ?? null
}

export function useConversationRuntime(
  currentSessionId: string | null,
  initialConnectionStatus: ConnectionStatus = 'disconnected'
) {
  const wsRef = useRef<SessionConversationWebSocket | null>(null)
  const connectedSessionIdRef = useRef<string | null>(null)
  const connectVersionRef = useRef(0)

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(initialConnectionStatus)
  const [isCancelling, setIsCancelling] = useState(false)
  const [retryInfo, setRetryInfo] = useState<LlmRetryDto | null>(null)

  const closeWebSocket = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    connectedSessionIdRef.current = null
    setConnectionStatus('disconnected')
  }, [])

  const refreshSnapshot = useCallback(async (sessionId: string) => {
    const response = await conversationApi.getConversation(sessionId)
    useConversationStore.getState().setSnapshot(sessionId, response.data)
  }, [])

  const queueSnapshotRefreshRef = useRef(
    createSnapshotRefreshQueue(async (sessionId: string) => {
      await refreshSnapshot(sessionId)
    })
  )

  const queueSnapshotRefresh = useCallback((sessionId: string) => {
    queueSnapshotRefreshRef.current(sessionId)
  }, [])

  const connectSession = useCallback(async (sessionId: string) => {
    if (
      connectedSessionIdRef.current === sessionId &&
      wsRef.current?.isConnected()
    ) {
      return
    }

    const connectVersion = connectVersionRef.current + 1
    connectVersionRef.current = connectVersion

    closeWebSocket()
    setConnectionStatus('connecting')

    const response = await conversationApi.getConversation(sessionId)
    if (connectVersion !== connectVersionRef.current) {
      return
    }

    useConversationStore.getState().setSnapshot(sessionId, response.data)

    const ws = new SessionConversationWebSocket()
    ws.on('connection:open', () => {
      setConnectionStatus('connected')
    })
    ws.on('connection:closed', () => {
      setConnectionStatus('disconnected')
      setIsCancelling(false)
    })
    ws.on('conversation:error', (data) => {
      console.error('Conversation websocket error:', data)
      setIsCancelling(false)
    })
    ws.on('conversation:event', (rawEvent) => {
      const event = toConversationEvent(rawEvent)
      useConversationStore.getState().applyEvent(sessionId, event)

      if (!INCREMENTAL_EVENT_TYPES.has(event.eventType)) {
        queueSnapshotRefresh(sessionId)
      }

      if (event.eventType === 'run.cancelled' || event.eventType === 'run.failed' || event.eventType === 'run.completed') {
        setIsCancelling(false)
        setRetryInfo(null)
        useConversationStore.getState().setPlan(sessionId, null)
      }
    })
    ws.on('conversation:live_event', (rawLiveEvent) => {
      useConversationStore.getState().applyLiveEvent(sessionId, toConversationLiveMessage(rawLiveEvent))
      setRetryInfo(null)
    })
    ws.on('conversation:live_state', (rawLiveState) => {
      useConversationStore.getState().setLiveState(sessionId, toConversationLiveMessage(rawLiveState))
      setRetryInfo(null)
    })
    ws.on('conversation:resync_required', () => {
      queueSnapshotRefresh(sessionId)
    })
    ws.on('llm:retry', (data) => {
      setRetryInfo(data)
    })
    ws.on('plan:updated', (data: PlanDto) => {
      useConversationStore.getState().setPlan(sessionId, {
        goal: data.goal,
        steps: data.steps,
        current_step_index: data.current_step_index,
      })
    })

    await ws.connect(sessionId)
    if (connectVersion !== connectVersionRef.current) {
      ws.close()
      return
    }

    ws.sendSync(response.data.session.lastEventSeq)
    wsRef.current = ws
    connectedSessionIdRef.current = sessionId
  }, [closeWebSocket, queueSnapshotRefresh])

  const startTurn = useCallback(async (payload: StartTurnPayload) => {
    const content = payload.message.trim()
    if (!content) {
      return
    }

    await connectSession(payload.sessionId)

    wsRef.current?.startTurn({
      content,
      providerId: payload.providerId,
      modelId: payload.modelId,
    })
  }, [connectSession])

  const cancelRun = useCallback(() => {
    const sessionId = currentSessionId ?? connectedSessionIdRef.current
    if (!sessionId) {
      return
    }

    const conversation = useConversationStore.getState().conversationsBySessionId[sessionId]
    const runId = resolveActiveRunId(conversation)
    if (!runId) {
      return
    }

    if (!wsRef.current?.isConnected()) {
      return
    }

    setIsCancelling(true)
    wsRef.current?.cancelRun(runId)
  }, [currentSessionId])

  const resetConversationRuntime = useCallback(() => {
    const sessionId = currentSessionId ?? connectedSessionIdRef.current
    closeWebSocket()
    setIsCancelling(false)

    if (sessionId) {
      useConversationStore.getState().clearConversation(sessionId)
    }
  }, [closeWebSocket, currentSessionId])

  useEffect(() => {
    if (!currentSessionId) {
      closeWebSocket()
      setIsCancelling(false)
      return
    }

    connectSession(currentSessionId).catch((error) => {
      console.error('Failed to initialize conversation runtime:', error)
      setConnectionStatus('disconnected')
    })
  }, [closeWebSocket, connectSession, currentSessionId])

  useEffect(() => {
    return () => {
      closeWebSocket()
    }
  }, [closeWebSocket])

  return {
    connectionStatus,
    isCancelling,
    retryInfo,
    startTurn,
    cancelRun,
    resetConversationRuntime,
  }
}
