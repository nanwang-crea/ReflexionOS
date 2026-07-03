import { useCallback, useEffect, useRef, useState } from 'react'
import { conversationApi } from '@/features/conversation/api/conversation.api'
import {
  findSessionIdByRunId,
  useConversationStore,
} from '@/features/conversation/stores/conversation.store'
import { useSessionStore } from '@/features/sessions/stores/session.store'
import { resetSession } from '@/features/sessions/session.actions'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'
import type { ConnectionStatus } from '@/features/workspace/types'
import type { LlmRetryDto, PlanDto } from '@/services/sessionConversationWebSocket'
import {
  SessionConversationWebSocket,
  type SessionConversationEventDto,
  type SessionConversationLiveMessageDto,
} from '@/services/sessionConversationWebSocket'
import type { ConversationEvent, ConversationLiveMessage } from '@/types/conversation'
import { useToastStore } from '@/shared/stores/toast.store'
import { resolveActiveRunId, resolveActiveRunStatus, ACTIVE_RUN_STATUSES } from '@/utils/activeRun'
import { useSubAgentEventsStore } from '@/hooks/useSubAgentEvents'
import type { SubAgentEventDto } from '@/services/sessionConversationWebSocket'

interface StartTurnPayload {
  sessionId: string
  message: string
  providerId?: string | null
  modelId?: string | null
  attachmentIds?: string[]
}

const SNAPSHOT_SKIP_EVENT_TYPES = new Set([
  'message.payload_updated',
  'message.content_committed',
])

const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000
const RECONNECT_MAX_ATTEMPTS = 10
const LIVE_EVENT_FLUSH_INTERVAL_MS = 50

// 同时保持的活跃后台连接上限。当前会话必连，其余活跃会话按优先级连接，
// 超出上限的会话降级为“切回时补拉”模式，不长期占用连接。
const MAX_ACTIVE_CONNECTIONS = 5

// 每个会话独立的连接运行时状态：websocket 实例、连接版本号、重连计数与定时器、
// 以及该会话自己的实时事件节流缓冲。多会话并行时，各会话互不干扰。
interface SessionConnection {
  sessionId: string
  ws: SessionConversationWebSocket | null
  connectVersion: number
  reconnectAttempt: number
  reconnectTimer: ReturnType<typeof setTimeout> | null
  pendingLiveEvent: ConversationLiveMessage | null
  liveEventFlushTimer: ReturnType<typeof setTimeout> | null
}

function createSnapshotRefreshQueue(
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

const VALID_MESSAGE_TYPES = new Set(['assistant_message', 'tool_trace'])
const VALID_STREAM_STATES = new Set(['idle', 'streaming', 'completed', 'failed', 'cancelled'])

function isValidMessageType(value: unknown): value is ConversationLiveMessage['messageType'] {
  return typeof value === 'string' && VALID_MESSAGE_TYPES.has(value)
}

function isValidStreamState(value: unknown): value is ConversationLiveMessage['streamState'] {
  return typeof value === 'string' && VALID_STREAM_STATES.has(value)
}

function toConversationLiveMessage(message: SessionConversationLiveMessageDto): ConversationLiveMessage {
  const messageType = isValidMessageType(message.message_type)
    ? message.message_type
    : 'assistant_message'
  const streamState = isValidStreamState(message.stream_state)
    ? message.stream_state
    : 'streaming'
  return {
    sessionId: message.session_id,
    turnId: message.turn_id,
    runId: message.run_id,
    messageId: message.message_id,
    messageType,
    contentText: message.content_text,
    streamState,
    delta: message.delta,
    payloadJson: message.payload_json,
  }
}

export function useConversationRuntime(
  currentSessionId: string | null,
  initialConnectionStatus: ConnectionStatus = 'disconnected'
) {
  // 按 sessionId 管理多条连接。connectionsRef 是连接运行时真值（命令式），
  // 下面三份 state 是给 UI 派生用的镜像，仅当前会话的切片会被读取并触发渲染。
  const connectionsRef = useRef<Map<string, SessionConnection>>(new Map())

  // 已经为某会话弹过“同步异常 / 断连”提示的集合，用于去重，避免同一会话
  // 重连耗尽时反复轰炸 toast。会话重连成功后从集合移除，允许下次再提示。
  const degradeToastShownRef = useRef<Set<string>>(new Set())

  const [connectionStatusBySessionId, setConnectionStatusBySessionId] =
    useState<Record<string, ConnectionStatus>>({})
  const [isCancellingBySessionId, setIsCancellingBySessionId] =
    useState<Record<string, boolean>>({})
  const [retryInfoBySessionId, setRetryInfoBySessionId] =
    useState<Record<string, LlmRetryDto | null>>({})

  // 订阅“当前有活跃 run 的后台会话”签名，用于驱动连接调度在后台会话
  // 由空闲变活跃（或反之）时重新运行。直接订阅 conversationsBySessionId 会
  // 在每个流式事件都触发，这里收敛成稳定字符串，仅活跃集合变化时才变。
  const activeSessionsSignature = useConversationStore((state) => {
    const activeIds: string[] = []
    for (const [sessionId, conversation] of Object.entries(state.conversationsBySessionId)) {
      const status = resolveActiveRunStatus(conversation)
      if (status !== null && ACTIVE_RUN_STATUSES.has(status)) {
        activeIds.push(sessionId)
      }
    }
    return activeIds.sort().join('|')
  })

  const scheduleReconnectRef = useRef<(sessionId: string) => void>(() => {})
  const connectSessionRef = useRef<(sessionId: string) => Promise<void>>(async () => {})

  // 始终保存最新的当前会话 id，供重连等回调判断“是不是用户正在看的会话”，
  // 避免闭包捕获到旧值（前台/后台的提示文案与降级处理不同）。
  const currentSessionIdRef = useRef<string | null>(currentSessionId)
  currentSessionIdRef.current = currentSessionId

  const setSessionConnectionStatus = useCallback((sessionId: string, status: ConnectionStatus) => {
    setConnectionStatusBySessionId((prev) => {
      if (prev[sessionId] === status) {
        return prev
      }
      return { ...prev, [sessionId]: status }
    })
  }, [])

  const setSessionCancelling = useCallback((sessionId: string, cancelling: boolean) => {
    setIsCancellingBySessionId((prev) => {
      if ((prev[sessionId] ?? false) === cancelling) {
        return prev
      }
      return { ...prev, [sessionId]: cancelling }
    })
  }, [])

  const setSessionRetryInfo = useCallback((sessionId: string, retry: LlmRetryDto | null) => {
    setRetryInfoBySessionId((prev) => {
      if ((prev[sessionId] ?? null) === retry) {
        return prev
      }
      return { ...prev, [sessionId]: retry }
    })
  }, [])

  const getOrCreateConnection = useCallback((sessionId: string): SessionConnection => {
    let connection = connectionsRef.current.get(sessionId)
    if (!connection) {
      connection = {
        sessionId,
        ws: null,
        connectVersion: 0,
        reconnectAttempt: 0,
        reconnectTimer: null,
        pendingLiveEvent: null,
        liveEventFlushTimer: null,
      }
      connectionsRef.current.set(sessionId, connection)
    }
    return connection
  }, [])

  const flushPendingLiveEvent = useCallback((sessionId: string) => {
    const connection = connectionsRef.current.get(sessionId)
    if (!connection) {
      return
    }

    if (connection.liveEventFlushTimer) {
      clearTimeout(connection.liveEventFlushTimer)
      connection.liveEventFlushTimer = null
    }

    const pending = connection.pendingLiveEvent
    if (!pending) {
      return
    }

    connection.pendingLiveEvent = null
    useConversationStore.getState().applyLiveEvent(sessionId, pending)
  }, [])

  const scheduleLiveEventFlush = useCallback((
    sessionId: string,
    liveMessage: ConversationLiveMessage
  ) => {
    const connection = getOrCreateConnection(sessionId)

    const isTerminal = liveMessage.streamState === 'completed'
      || liveMessage.streamState === 'failed'
      || liveMessage.streamState === 'cancelled'

    if (isTerminal) {
      flushPendingLiveEvent(sessionId)
      useConversationStore.getState().applyLiveEvent(sessionId, liveMessage)
      return
    }

    if (!connection.liveEventFlushTimer && !connection.pendingLiveEvent) {
      useConversationStore.getState().applyLiveEvent(sessionId, liveMessage)
      connection.liveEventFlushTimer = setTimeout(() => {
        flushPendingLiveEvent(sessionId)
      }, LIVE_EVENT_FLUSH_INTERVAL_MS)
      return
    }

    connection.pendingLiveEvent = liveMessage
    if (connection.liveEventFlushTimer) {
      return
    }

    connection.liveEventFlushTimer = setTimeout(() => {
      flushPendingLiveEvent(sessionId)
    }, LIVE_EVENT_FLUSH_INTERVAL_MS)
  }, [getOrCreateConnection, flushPendingLiveEvent])

  // 关闭并清理某个会话的连接：停掉重连定时器、刷出残留实时事件、关闭 websocket。
  const closeSessionConnection = useCallback((sessionId: string) => {
    const connection = connectionsRef.current.get(sessionId)
    if (!connection) {
      return
    }

    flushPendingLiveEvent(sessionId)
    if (connection.reconnectTimer) {
      clearTimeout(connection.reconnectTimer)
      connection.reconnectTimer = null
    }
    connection.reconnectAttempt = 0
    // 让进行中的连接版本作废，防止 await connect 返回后误用旧连接。
    connection.connectVersion += 1
    connection.ws?.close()
    connection.ws = null
    setSessionConnectionStatus(sessionId, 'disconnected')
  }, [flushPendingLiveEvent, setSessionConnectionStatus])

  const refreshSnapshot = useCallback(async (sessionId: string) => {
    const response = await conversationApi.getConversationPaginated(sessionId, { limit: 20 })
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
    const connection = getOrCreateConnection(sessionId)

    if (connection.ws?.isConnected()) {
      return
    }

    const connectVersion = connection.connectVersion + 1
    connection.connectVersion = connectVersion

    // 关闭该会话上可能存在的旧连接（不影响其他会话）。
    if (connection.reconnectTimer) {
      clearTimeout(connection.reconnectTimer)
      connection.reconnectTimer = null
    }
    connection.ws?.close()
    connection.ws = null
    setSessionConnectionStatus(sessionId, 'connecting')

    const response = await conversationApi.getConversationPaginated(sessionId, { limit: 20 })
    if (connectVersion !== connection.connectVersion) {
      return
    }

    useConversationStore.getState().setSnapshot(sessionId, response.data)

    const ws = new SessionConversationWebSocket()
    ws.on('connection:open', () => {
      setSessionConnectionStatus(sessionId, 'connected')
      connection.reconnectAttempt = 0
      if (connection.reconnectTimer) {
        clearTimeout(connection.reconnectTimer)
        connection.reconnectTimer = null
      }
      // 连接恢复：清除同步异常标记与提示去重，允许后续再次提示。
      degradeToastShownRef.current.delete(sessionId)
      useWorkspaceStore.getState().clearSessionSyncHealth(sessionId)
    })
    ws.on('connection:closed', () => {
      setSessionConnectionStatus(sessionId, 'disconnected')
      setSessionCancelling(sessionId, false)
      scheduleReconnectRef.current(sessionId)
    })
    ws.on('conversation:error', (data) => {
      console.error('Conversation websocket error:', data)
      const message = typeof data.message === 'string' ? data.message : '对话发生错误'
      useToastStore.getState().addToast('error', message)
      setSessionCancelling(sessionId, false)
    })
    ws.on('conversation:event', (rawEvent) => {
      const event = toConversationEvent(rawEvent)
      useConversationStore.getState().applyEvent(sessionId, event)

      if (!SNAPSHOT_SKIP_EVENT_TYPES.has(event.eventType)) {
        queueSnapshotRefresh(sessionId)
      }

      if (event.eventType === 'run.cancelled' || event.eventType === 'run.failed' || event.eventType === 'run.completed') {
        setSessionCancelling(sessionId, false)
        setSessionRetryInfo(sessionId, null)
        useConversationStore.getState().setPlan(sessionId, null)
      }
    })
    ws.on('conversation:live_event', (rawLiveEvent) => {
      scheduleLiveEventFlush(sessionId, toConversationLiveMessage(rawLiveEvent))
      setSessionRetryInfo(sessionId, null)
    })
    ws.on('conversation:live_state', (rawLiveState) => {
      flushPendingLiveEvent(sessionId)
      useConversationStore.getState().setLiveState(sessionId, toConversationLiveMessage(rawLiveState))
      setSessionRetryInfo(sessionId, null)
    })
    ws.on('conversation:resync_required', (data) => {
      queueSnapshotRefresh(sessionId)
      const afterSeq = typeof data.after_seq === 'number' ? data.after_seq : 0
      ws.sendSync(afterSeq)
    })
    ws.on('llm:retry', (data) => {
      setSessionRetryInfo(sessionId, data)
    })
    ws.on('plan:updated', (data: PlanDto) => {
      useConversationStore.getState().setPlan(sessionId, {
        goal: data.goal,
        steps: data.steps,
      })
    })
    ws.on('plan:discarded', () => {
      useConversationStore.getState().setPlan(sessionId, null)
    })
    ws.on('plan:recovered', () => {
      useConversationStore.getState().setPlan(sessionId, null)
    })
    ws.on('session:mode_changed', (data: { session_id: string; mode: string }) => {
      if (data.mode === 'build' || data.mode === 'plan') {
        useConversationStore.getState().setAgentMode(sessionId, data.mode)
      }
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
    ws.on('sub_agent:event', (data: SubAgentEventDto) => {
      useSubAgentEventsStore.getState().addEvent(data)
    })

    await ws.connect(sessionId)
    if (connectVersion !== connection.connectVersion) {
      ws.close()
      return
    }

    ws.sendSync(response.data.session.lastEventSeq)
    connection.ws = ws
    connection.reconnectAttempt = 0
  }, [
    getOrCreateConnection,
    setSessionConnectionStatus,
    setSessionCancelling,
    setSessionRetryInfo,
    flushPendingLiveEvent,
    queueSnapshotRefresh,
    scheduleLiveEventFlush,
  ])

  useEffect(() => {
    connectSessionRef.current = connectSession
  }, [connectSession])

  const scheduleReconnect = useCallback((sessionId: string) => {
    const connection = connectionsRef.current.get(sessionId)
    if (!connection) {
      return
    }

    const attempt = connection.reconnectAttempt + 1
    if (attempt > RECONNECT_MAX_ATTEMPTS) {
      // 重连耗尽：标记会话为同步异常（不改 run 业务状态），降级为切回补拉模式。
      useWorkspaceStore.getState().markSessionSyncDegraded(sessionId)

      // 同一会话只提示一次，避免反复轰炸；重连成功后会重置去重标记。
      if (!degradeToastShownRef.current.has(sessionId)) {
        degradeToastShownRef.current.add(sessionId)
        const isCurrent = sessionId === currentSessionIdRef.current
        useToastStore.getState().addToast(
          'error',
          isCurrent
            ? 'WebSocket 连接断开，请刷新页面重连'
            : '后台会话同步中断，将在切回时重新拉取最新状态',
        )
      }
      return
    }
    connection.reconnectAttempt = attempt
    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt - 1),
      RECONNECT_MAX_DELAY_MS
    )
    connection.reconnectTimer = setTimeout(() => {
      connection.reconnectTimer = null
      connectSessionRef.current(sessionId).catch((error) => {
        console.error('Reconnect failed:', error)
        scheduleReconnectRef.current(sessionId)
      })
    }, delay)
  }, [])

  useEffect(() => {
    scheduleReconnectRef.current = scheduleReconnect
  }, [scheduleReconnect])

  // 按 runId 路由到所属会话的连接。当前会话操作直接用 currentSessionId；
  // 审批 / 拒绝 / 重跑等只带 runId 的操作，先反查 sessionId 再选对应连接。
  const resolveConnectionByRunId = useCallback((runId: string): SessionConnection | null => {
    const sessionId = findSessionIdByRunId(
      useConversationStore.getState().conversationsBySessionId,
      runId
    )
    if (!sessionId) {
      return null
    }
    return connectionsRef.current.get(sessionId) ?? null
  }, [])

  // 按 sessionId 直接获取连接。用于 SubAgent 场景，已知 parentSessionId。
  const resolveConnectionBySessionId = useCallback((sessionId: string): SessionConnection | null => {
    return connectionsRef.current.get(sessionId) ?? null
  }, [])

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
      setSessionConnectionStatus(payload.sessionId, 'disconnected')
      return
    }

    connectionsRef.current.get(payload.sessionId)?.ws?.startTurn({
      content,
      providerId: payload.providerId,
      modelId: payload.modelId,
      attachmentIds: payload.attachmentIds,
    })
  }, [connectSession, setSessionConnectionStatus])

  const cancelRun = useCallback(() => {
    if (!currentSessionId) {
      return
    }

    const conversation = useConversationStore.getState().conversationsBySessionId[currentSessionId]
    const runId = resolveActiveRunId(conversation)
    if (!runId) {
      return
    }

    const ws = connectionsRef.current.get(currentSessionId)?.ws
    if (!ws?.isConnected()) {
      return
    }

    setSessionCancelling(currentSessionId, true)
    ws.cancelRun(runId)
  }, [currentSessionId, setSessionCancelling])

  const approveTool = useCallback((runId: string, approvalId: string, parentSessionId?: string) => {
    // 如果提供了 parentSessionId（SubAgent 场景），优先使用它查找连接
    const ws = parentSessionId
      ? resolveConnectionBySessionId(parentSessionId)?.ws
      : resolveConnectionByRunId(runId)?.ws
    if (!ws?.isConnected()) {
      return
    }

    ws.approveTool({ runId, approvalId, decision: 'allow_once' })
  }, [resolveConnectionByRunId, resolveConnectionBySessionId])

  const denyTool = useCallback((runId: string, approvalId: string, parentSessionId?: string) => {
    // 如果提供了 parentSessionId（SubAgent 场景），优先使用它查找连接
    const ws = parentSessionId
      ? resolveConnectionBySessionId(parentSessionId)?.ws
      : resolveConnectionByRunId(runId)?.ws
    if (!ws?.isConnected()) {
      return
    }

    ws.denyTool({ runId, approvalId })
  }, [resolveConnectionByRunId, resolveConnectionBySessionId])

  const trustTool = useCallback((runId: string, approvalId: string, parentSessionId?: string) => {
    // 如果提供了 parentSessionId（SubAgent 场景），优先使用它查找连接
    const ws = parentSessionId
      ? resolveConnectionBySessionId(parentSessionId)?.ws
      : resolveConnectionByRunId(runId)?.ws
    if (!ws?.isConnected()) {
      return
    }

    ws.approveTool({ runId, approvalId, decision: 'trust_and_allow' })
  }, [resolveConnectionByRunId, resolveConnectionBySessionId])

  const editAndRerun = useCallback((payload: {
    messageId: string
    newContent?: string | null
    providerId?: string | null
    modelId?: string | null
  }) => {
    if (!currentSessionId) {
      return
    }

    const ws = connectionsRef.current.get(currentSessionId)?.ws
    if (!ws?.isConnected()) {
      return
    }

    ws.editAndRerun(payload)
  }, [currentSessionId])

  const setMode = useCallback((mode: 'build' | 'plan') => {
    if (!currentSessionId) {
      return
    }

    const ws = connectionsRef.current.get(currentSessionId)?.ws
    if (!ws?.isConnected()) {
      return
    }
    ws.send({
      type: 'session:set_mode',
      data: { mode },
    })
  }, [currentSessionId])

  const resetConversationRuntime = useCallback(async () => {
    if (!currentSessionId) {
      return
    }

    // 先清后端历史（先停后清），成功后才同步前端真值与显示；失败则不动任何状态。
    try {
      await resetSession(currentSessionId)
    } catch (error) {
      const message = error instanceof Error ? error.message : '重置对话失败'
      useToastStore.getState().addToast('error', `重置对话失败: ${message}`)
      return
    }

    // resetSession 已用返回的 Session 回写 session.store（列表真值）。
    // 此处补齐：清聊天区快照、回退未读基线、关连接与取消标志。
    useConversationStore.getState().clearConversation(currentSessionId)
    useWorkspaceStore.getState().resetSessionSeen(currentSessionId)
    closeSessionConnection(currentSessionId)
    setSessionCancelling(currentSessionId, false)
  }, [closeSessionConnection, currentSessionId, setSessionCancelling])

  // 连接调度：当前会话必连；其余活跃会话（运行中 / 待审批等）按优先级补连，
  // 总连接数不超过上限；超出上限或已空闲的会话连接被回收，降级为切回补拉。
  useEffect(() => {
    const conversationsBySessionId = useConversationStore.getState().conversationsBySessionId

    // 收集需要保持连接的会话：当前会话 + 仍有活跃 run 的后台会话。
    const desiredSessionIds: string[] = []
    if (currentSessionId) {
      desiredSessionIds.push(currentSessionId)
    }

    const backgroundActiveSessionIds = Object.entries(conversationsBySessionId)
      .filter(([sessionId]) => sessionId !== currentSessionId)
      .filter(([, conversation]) => {
        const status = resolveActiveRunStatus(conversation)
        return status !== null && ACTIVE_RUN_STATUSES.has(status)
      })
      .map(([sessionId]) => sessionId)

    for (const sessionId of backgroundActiveSessionIds) {
      if (desiredSessionIds.length >= MAX_ACTIVE_CONNECTIONS) {
        break
      }
      desiredSessionIds.push(sessionId)
    }

    const desiredSet = new Set(desiredSessionIds)

    // 回收不再需要保持的连接（含被降级会话），但保留当前会话。
    for (const sessionId of connectionsRef.current.keys()) {
      if (!desiredSet.has(sessionId)) {
        closeSessionConnection(sessionId)
      }
    }

    // 为需要的会话建立 / 维持连接。
    for (const sessionId of desiredSessionIds) {
      const connection = connectionsRef.current.get(sessionId)
      if (connection?.ws?.isConnected()) {
        continue
      }
      connectSession(sessionId).catch((error) => {
        console.error('Failed to connect conversation session:', error)
        // 当前会话连接失败要明确提示用户；后台会话失败静默，靠重连/补拉兜底。
        if (sessionId === currentSessionId) {
          const message = error instanceof Error ? error.message : '连接失败'
          useToastStore.getState().addToast('error', `对话连接失败: ${message}`)
          setSessionConnectionStatus(sessionId, 'disconnected')
        }
      })
    }
    // activeSessionsSignature 在依赖里：后台会话由空闲变活跃 / 活跃变空闲时，
    // 调度会重新运行，从而补连新活跃会话或回收已结束会话的连接。
  }, [currentSessionId, activeSessionsSignature, closeSessionConnection, connectSession, setSessionConnectionStatus])

  // 切回被降级会话时，立刻强制补拉一次快照，让用户即时看到离线/降级期间
  // 发生的终态变化，而不必等 websocket 重连成功。补拉成功即清除异常标记；
  // 后续 websocket 若重连成功也会再清一次（幂等）。
  useEffect(() => {
    if (!currentSessionId) {
      return
    }
    const health = useWorkspaceStore.getState().sessionSyncHealthBySessionId[currentSessionId]
    if (health !== 'degraded') {
      return
    }

    refreshSnapshot(currentSessionId)
      .then(() => {
        useWorkspaceStore.getState().clearSessionSyncHealth(currentSessionId)
        degradeToastShownRef.current.delete(currentSessionId)
      })
      .catch((error) => {
        console.error('Failed to force-refresh degraded session:', error)
      })
  }, [currentSessionId, refreshSnapshot])

  useEffect(() => {
    const connections = connectionsRef.current
    return () => {
      for (const sessionId of connections.keys()) {
        const connection = connections.get(sessionId)
        if (!connection) {
          continue
        }
        flushPendingLiveEvent(sessionId)
        if (connection.reconnectTimer) {
          clearTimeout(connection.reconnectTimer)
          connection.reconnectTimer = null
        }
        connection.connectVersion += 1
        connection.ws?.close()
        connection.ws = null
      }
      connections.clear()
    }
  }, [flushPendingLiveEvent])

  const loadMore = useCallback(async (sessionId: string, beforeTurnId: string) => {
    const response = await conversationApi.getConversationPaginated(sessionId, { limit: 20, beforeTurn: beforeTurnId })
    const snapshot = response.data
    useConversationStore.getState().prependMessages(sessionId, snapshot.messages, snapshot.turns, snapshot.runs)
    useConversationStore.getState().setPagination(sessionId, {
      hasMore: snapshot.hasMore,
      nextBeforeTurnId: snapshot.nextBeforeTurnId,
    })
  }, [])

  // 对 UI 只暴露“当前会话”的连接状态切片，保持原有单会话调用契约不变。
  const connectionStatus: ConnectionStatus = currentSessionId
    ? connectionStatusBySessionId[currentSessionId] ?? initialConnectionStatus
    : initialConnectionStatus
  const isCancelling = currentSessionId
    ? isCancellingBySessionId[currentSessionId] ?? false
    : false
  const retryInfo = currentSessionId
    ? retryInfoBySessionId[currentSessionId] ?? null
    : null

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

export { createSnapshotRefreshQueue }
