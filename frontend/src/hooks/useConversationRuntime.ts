import { useCallback, useEffect, useRef, useState } from 'react'
import { conversationApi } from '@/features/conversation/conversationApi'
import { useConversationStore } from '@/features/conversation/conversationStore'
import { useSessionStore } from '@/features/sessions/sessionStore'
import type { ConnectionStatus } from '@/features/workspace/types'
import type { LlmRetryDto, PlanDto } from '@/services/sessionConversationWebSocket'
import {
  SessionConversationWebSocket,
  type SessionConversationEventDto,
  type SessionConversationLiveMessageDto,
} from '@/services/sessionConversationWebSocket'
import type { ConversationEvent, ConversationLiveMessage } from '@/types/conversation'
import { useToastStore } from '@/stores/toastStore'
import { resolveActiveRunId } from '@/utils/activeRun'

interface StartTurnPayload {
  sessionId: string
  message: string
  providerId?: string | null
  modelId?: string | null
}

const INCREMENTAL_EVENT_TYPES = new Set([
  'message.payload_updated',
])

const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000
const RECONNECT_MAX_ATTEMPTS = 10
const LIVE_EVENT_FLUSH_INTERVAL_MS = 50

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
          useToastStore.getState().addToast('error', `对话刷新失败: ${error instanceof Error ? error.message : '刷新对话失败'}`)
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
    payloadJson: message.payload_json,
  }
}

export function useConversationRuntime(
  currentSessionId: string | null,
  initialConnectionStatus: ConnectionStatus = 'disconnected'
) {
  const wsRef = useRef<SessionConversationWebSocket | null>(null)
  const connectedSessionIdRef = useRef<string | null>(null)
  const connectVersionRef = useRef(0)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const scheduleReconnectRef = useRef<(sessionId: string) => void>(() => {})
  const pendingLiveEventRef = useRef<{
    sessionId: string
    liveMessage: ConversationLiveMessage
  } | null>(null)
  const liveEventFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(initialConnectionStatus)
  const [isCancelling, setIsCancelling] = useState(false)
  const [retryInfo, setRetryInfo] = useState<LlmRetryDto | null>(null)

  const flushPendingLiveEvent = useCallback(() => {
    if (liveEventFlushTimerRef.current) {
      clearTimeout(liveEventFlushTimerRef.current)
      liveEventFlushTimerRef.current = null
    }

    const pending = pendingLiveEventRef.current
    if (!pending) {
      return
    }

    pendingLiveEventRef.current = null
    useConversationStore.getState().applyLiveEvent(pending.sessionId, pending.liveMessage)
  }, [])

  const scheduleLiveEventFlush = useCallback((
    sessionId: string,
    liveMessage: ConversationLiveMessage
  ) => {
    const isTerminal = liveMessage.streamState === 'completed'
      || liveMessage.streamState === 'failed'
      || liveMessage.streamState === 'cancelled'

    if (isTerminal) {
      flushPendingLiveEvent()
      useConversationStore.getState().applyLiveEvent(sessionId, liveMessage)
      return
    }

    if (!liveEventFlushTimerRef.current && !pendingLiveEventRef.current) {
      useConversationStore.getState().applyLiveEvent(sessionId, liveMessage)
      liveEventFlushTimerRef.current = setTimeout(() => {
        flushPendingLiveEvent()
      }, LIVE_EVENT_FLUSH_INTERVAL_MS)
      return
    }

    pendingLiveEventRef.current = { sessionId, liveMessage }
    if (liveEventFlushTimerRef.current) {
      return
    }

    liveEventFlushTimerRef.current = setTimeout(() => {
      flushPendingLiveEvent()
    }, LIVE_EVENT_FLUSH_INTERVAL_MS)
  }, [flushPendingLiveEvent])

  const closeWebSocket = useCallback(() => {
    flushPendingLiveEvent()
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    reconnectAttemptRef.current = 0
    wsRef.current?.close()
    wsRef.current = null
    connectedSessionIdRef.current = null
    setConnectionStatus('disconnected')
  }, [flushPendingLiveEvent])

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

    const response = await conversationApi.getConversationPaginated(sessionId, { limit: 20 })
    if (connectVersion !== connectVersionRef.current) {
      return
    }

    useConversationStore.getState().setSnapshot(sessionId, response.data)

    const ws = new SessionConversationWebSocket()
    ws.on('connection:open', () => {
      setConnectionStatus('connected')
      reconnectAttemptRef.current = 0
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    })
    ws.on('connection:closed', () => {
      setConnectionStatus('disconnected')
      setIsCancelling(false)
      const sessionId = connectedSessionIdRef.current
      if (sessionId) {
        scheduleReconnectRef.current(sessionId)
      }
    })
    ws.on('conversation:error', (data) => {
      console.error('Conversation websocket error:', data)
      const message = typeof data.message === 'string' ? data.message : '对话发生错误'
      useToastStore.getState().addToast('error', message)
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
      scheduleLiveEventFlush(sessionId, toConversationLiveMessage(rawLiveEvent))
      setRetryInfo(null)
    })
    ws.on('conversation:live_state', (rawLiveState) => {
      flushPendingLiveEvent()
      useConversationStore.getState().setLiveState(sessionId, toConversationLiveMessage(rawLiveState))
      setRetryInfo(null)
    })
    ws.on('conversation:resync_required', (data) => {
      queueSnapshotRefresh(sessionId)
      const afterSeq = typeof data.after_seq === 'number' ? data.after_seq : 0
      ws.sendSync(afterSeq)
    })
    ws.on('llm:retry', (data) => {
      setRetryInfo(data)
    })
    ws.on('plan:updated', (data: PlanDto) => {
      useConversationStore.getState().setPlan(sessionId, {
        goal: data.goal,
        steps: data.steps,
        currentStepIndex: data.current_step_index,
      })
    })
    ws.on('session:mode_changed', (data: { session_id: string; mode: string }) => {
      useConversationStore.getState().setAgentMode(sessionId, data.mode as import('@/types/conversation').AgentMode)
    })
    ws.on('session:title_updated', (data) => {
      const store = useSessionStore.getState()
      const sessionsByProjectId = store.sessionsByProjectId
      for (const [projectId, sessions] of Object.entries(sessionsByProjectId)) {
        const session = sessions.find((s) => s.id === data.session_id)
        if (session) {
          store.upsertSession(projectId, { ...session, title: data.title })
          break
        }
      }
    })

    await ws.connect(sessionId)
    if (connectVersion !== connectVersionRef.current) {
      ws.close()
      return
    }

    ws.sendSync(response.data.session.lastEventSeq)
    wsRef.current = ws
    connectedSessionIdRef.current = sessionId
    reconnectAttemptRef.current = 0
  }, [closeWebSocket, flushPendingLiveEvent, queueSnapshotRefresh, scheduleLiveEventFlush])

  const scheduleReconnect = useCallback((sessionId: string) => {
    const attempt = reconnectAttemptRef.current + 1
    if (attempt > RECONNECT_MAX_ATTEMPTS) {
      useToastStore.getState().addToast('error', 'WebSocket 连接断开，请刷新页面重连')
      return
    }
    reconnectAttemptRef.current = attempt
    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt - 1),
      RECONNECT_MAX_DELAY_MS
    )
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null
      connectSession(sessionId).catch((error) => {
        console.error('Reconnect failed:', error)
        scheduleReconnectRef.current(sessionId)
      })
    }, delay)
  }, [connectSession])

  useEffect(() => {
    scheduleReconnectRef.current = scheduleReconnect
  }, [scheduleReconnect])

  const startTurn = useCallback(async (payload: StartTurnPayload) => {
    const content = payload.message.trim()
    if (!content) {
      return
    }

    try {
      await connectSession(payload.sessionId)
    } catch (error) {
      console.error('Failed to connect session for startTurn:', error)
      const message = error instanceof Error ? error.message : '连接失败'
      useToastStore.getState().addToast('error', `发送消息失败: ${message}`)
      setConnectionStatus('disconnected')
      return
    }

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

  const approveTool = useCallback((runId: string, approvalId: string) => {
    if (!wsRef.current?.isConnected()) {
      return
    }

    wsRef.current.approveTool({ runId, approvalId, decision: 'allow_once' })
  }, [])

  const denyTool = useCallback((runId: string, approvalId: string) => {
    if (!wsRef.current?.isConnected()) {
      return
    }

    wsRef.current.denyTool({ runId, approvalId })
  }, [])

  const trustTool = useCallback((runId: string, approvalId: string) => {
    if (!wsRef.current?.isConnected()) {
      return
    }

    wsRef.current.approveTool({ runId, approvalId, decision: 'trust_and_allow' })
  }, [])

  const editAndRerun = useCallback((payload: {
    messageId: string
    newContent?: string | null
    providerId?: string | null
    modelId?: string | null
  }) => {
    if (!wsRef.current?.isConnected()) {
      return
    }

    wsRef.current.editAndRerun(payload)
  }, [])

  const setMode = useCallback((mode: 'build' | 'plan') => {
    if (!wsRef.current?.isConnected()) {
      return
    }
    wsRef.current.send({
      type: 'session:set_mode',
      data: { mode },
    })
  }, [])

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
      const message = error instanceof Error ? error.message : '连接失败'
      useToastStore.getState().addToast('error', `对话连接失败: ${message}`)
      setConnectionStatus('disconnected')
    })
  }, [closeWebSocket, connectSession, currentSessionId])

  useEffect(() => {
    return () => {
      flushPendingLiveEvent()
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      closeWebSocket()
    }
  }, [closeWebSocket, flushPendingLiveEvent])

  const loadMore = useCallback(async (sessionId: string, beforeMessageId: string) => {
    const response = await conversationApi.getConversationPaginated(sessionId, { limit: 20, before: beforeMessageId })
    const snapshot = response.data
    useConversationStore.getState().prependMessages(sessionId, snapshot.messages, snapshot.turns, snapshot.runs)
    useConversationStore.getState().setHasMore(sessionId, snapshot.hasMore)
  }, [])

  return {
    connectionStatus,
    isCancelling,
    retryInfo,
    startTurn,
    cancelRun,
    approveTool,
    denyTool,
    trustTool,
    editAndRerun,
    setMode,
    resetConversationRuntime,
    loadMore,
  }
}
