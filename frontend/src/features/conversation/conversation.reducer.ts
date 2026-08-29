/**
 * 文件功能：会话状态的纯函数 reducer（状态转换逻辑）
 * 文件描述：定义如何把后端会话快照（snapshot）、实时事件（event）、流式增量消息（live message）
 *          合并/应用到本地 ConversationState 上，供 zustand store 调用。
 * 核心逻辑：
 *   1. 快照合并：以后端快照为准，但保留仍在流式输出、尚未落库的助手消息（避免闪断）；
 *      同时兼容"向前加载更多历史"场景，保留本地已加载但快照未包含的历史轮次/消息。
 *   2. 事件应用：按事件类型（turn.created / run.* / message.* / messages.truncated 等）
 *      对状态做增量更新，并以 seq（事件序号）做幂等/乱序保护，只接受比 lastEventSeq 更新的事件。
 *   3. 子 agent 事件：事件类型带有 "sub_agent:" 前缀时先剥离前缀再按普通事件处理，
 *      delegate_call_id 保留在事件对象上供 UI 层判断展示方式。
 *   4. 实时状态：流式消息通过 upsert/删除占位消息的方式维护，不影响 lastEventSeq（因为不是持久化事件）。
 */
import type {
  ConversationEvent,
  ConversationLiveMessage,
  ConversationMessage,
  ConversationRun,
  ConversationSnapshot,
  ConversationState,
  ConversationStreamState,
  ConversationTurn,
} from '@/types/conversation'

/**
 * 函数名：isRecord
 * 入参：
 *   - value (unknown): 任意待判断的值
 * 功能：类型守卫，判断某个值是否为普通对象（非 null、非数组）
 * 运行逻辑：用 typeof 和 Array.isArray 组合判断
 * 出参：boolean（类型谓词 value is Record<string, unknown>） - 是否为普通对象
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 函数名：isValidRole
 * 入参：
 *   - value (unknown): 任意待判断的值，通常来自事件 payload 中的角色字段
 * 功能：类型守卫，判断值是否为合法的消息角色（user 或 assistant）
 * 运行逻辑：直接做值比较
 * 出参：boolean（类型谓词） - 是否为合法角色
 */
function isValidRole(value: unknown): value is ConversationMessage['role'] {
  return value === 'user' || value === 'assistant'
}

/**
 * 函数名：isValidMessageType
 * 入参：
 *   - value (unknown): 任意待判断的值，通常来自事件 payload 中的消息类型字段
 * 功能：类型守卫，判断值是否为合法的消息类型（用户消息/工具轨迹/助手消息）
 * 运行逻辑：直接做值比较
 * 出参：boolean（类型谓词） - 是否为合法消息类型
 */
function isValidMessageType(value: unknown): value is ConversationMessage['messageType'] {
  return value === 'user_message' || value === 'tool_trace' || value === 'assistant_message'
}

/**
 * 函数名：buildMessageOrder
 * 入参：
 *   - snapshot (ConversationSnapshot): 后端返回的会话快照，包含 turns 和 messages
 * 功能：根据快照中的轮次顺序和轮内消息顺序，计算出消息 id 的展示顺序
 * 运行逻辑：先建立 turnId -> turnIndex 的映射，再对消息按 (turnIndex, turnMessageIndex) 排序；
 *          找不到所属轮次的消息排到最后（用 MAX_SAFE_INTEGER 兜底）
 * 出参：string[] - 排好序的消息 id 列表
 */
function buildMessageOrder(snapshot: ConversationSnapshot): string[] {
  const turnIndexById = Object.fromEntries(snapshot.turns.map((turn) => [turn.id, turn.turnIndex]))

  return snapshot.messages
    .slice()
    .sort((left, right) => {
      const leftTurnIndex = turnIndexById[left.turnId] ?? Number.MAX_SAFE_INTEGER
      const rightTurnIndex = turnIndexById[right.turnId] ?? Number.MAX_SAFE_INTEGER
      return leftTurnIndex - rightTurnIndex || left.turnMessageIndex - right.turnMessageIndex
    })
    .map((message) => message.id)
}

/**
 * 函数名：mergeStreamingMessages
 * 入参：
 *   - previous (ConversationState | undefined): 应用快照前的本地状态（首次加载时为 undefined）
 *   - snapshot (ConversationSnapshot): 后端最新返回的会话快照
 * 功能：合并快照消息与本地仍在流式输出、尚未写入快照的助手消息，避免快照刷新时正在
 *      流式输出的内容被清空导致画面闪断
 * 运行逻辑：
 *   1. 无历史状态或当前会话没有 activeTurnId 时，直接采用快照数据；
 *   2. 找到当前活跃轮次对应的 activeRunId，若不存在则直接采用快照数据；
 *   3. 否则从本地状态中筛出属于该 run、仍处于 streaming 且快照中还没有的助手消息，
 *      将其追加到快照消息之后，保证流式内容不丢失。
 * 出参：{ messageOrder: string[]; messagesById: Record<string, ConversationMessage> } - 合并后的消息顺序与消息表
 */
function mergeStreamingMessages(
  previous: ConversationState | undefined,
  snapshot: ConversationSnapshot
): { messageOrder: string[]; messagesById: Record<string, ConversationMessage> } {
  const snapshotMessageOrder = buildMessageOrder(snapshot)
  const snapshotMessagesById = Object.fromEntries(snapshot.messages.map((message) => [message.id, message]))

  if (!previous || !snapshot.session.activeTurnId) {
    return {
      messageOrder: snapshotMessageOrder,
      messagesById: snapshotMessagesById,
    }
  }

  const activeRunId = snapshot.turns
    .find((turn) => turn.id === snapshot.session.activeTurnId)
    ?.activeRunId

  if (!activeRunId) {
    return {
      messageOrder: snapshotMessageOrder,
      messagesById: snapshotMessagesById,
    }
  }

  const carriedMessages = previous.messageOrder
    .map((messageId) => previous.messagesById[messageId])
    .filter((message): message is ConversationMessage => {
      return Boolean(
        message &&
        message.messageType === 'assistant_message' &&
        message.streamState === 'streaming' &&
        message.runId === activeRunId &&
        !(message.id in snapshotMessagesById)
      )
    })

  return {
    messageOrder: [
      ...snapshotMessageOrder,
      ...carriedMessages.map((message) => message.id),
    ],
    messagesById: {
      ...snapshotMessagesById,
      ...Object.fromEntries(carriedMessages.map((message) => [message.id, message])),
    },
  }
}

/**
 * 函数名：nextTurnMessageIndex
 * 入参：
 *   - state (ConversationState): 当前会话状态
 *   - turnId (string): 目标轮次 id
 * 功能：计算指定轮次下一条消息应使用的 turnMessageIndex（轮内消息序号）
 * 运行逻辑：遍历该轮次下所有已存在的消息，取最大 turnMessageIndex 后加 1
 * 出参：number - 下一条消息的轮内序号
 */
function nextTurnMessageIndex(state: ConversationState, turnId: string): number {
  const current = Object.values(state.messagesById)
    .filter((message) => message.turnId === turnId)
    .reduce((maxIndex, message) => Math.max(maxIndex, message.turnMessageIndex), 0)
  return current + 1
}

// 消息流式状态的终态集合：达到这些状态后消息内容不会再变化
const TERMINAL_STREAM_STATES = new Set<ConversationStreamState>(['completed', 'failed', 'cancelled'])

/**
 * 函数名：isTerminalStreamState
 * 入参：
 *   - state (ConversationStreamState): 消息的流式状态
 * 功能：判断消息流式状态是否已到达终态（不会再更新）
 * 运行逻辑：查表 TERMINAL_STREAM_STATES
 * 出参：boolean - 是否为终态
 */
function isTerminalStreamState(state: ConversationStreamState): boolean {
  return TERMINAL_STREAM_STATES.has(state)
}

/**
 * 函数名：upsertLiveAssistantMessage
 * 入参：
 *   - state (ConversationState): 当前会话状态
 *   - liveMessage (ConversationLiveMessage): 实时到达的助手消息增量（含最新全量 contentText）
 * 功能：将实时流式消息写入/更新到本地状态中的助手消息（不落库，仅用于即时展示）
 * 运行逻辑：
 *   1. 若消息已存在，则用最新内容/流式状态/payload 覆盖更新，若进入终态则记录 completedAt；
 *   2. 若消息不存在，则新建一条助手消息，turnMessageIndex 通过 nextTurnMessageIndex 计算；
 *   3. 若为新建消息，将其 id 追加到 messageOrder 末尾。
 * 出参：ConversationState - 更新后的会话状态
 */
function upsertLiveAssistantMessage(
  state: ConversationState,
  liveMessage: ConversationLiveMessage
): ConversationState {
  const currentMessage = state.messagesById[liveMessage.messageId]
  const timestamp = new Date().toISOString()

  const nextMessage: ConversationMessage = currentMessage
    ? {
        ...currentMessage,
        contentText: liveMessage.contentText,
        streamState: liveMessage.streamState,
        payloadJson: liveMessage.payloadJson
          ? {
              ...currentMessage.payloadJson,
              ...liveMessage.payloadJson,
            }
          : currentMessage.payloadJson,
        completedAt: isTerminalStreamState(liveMessage.streamState)
          ? timestamp
          : currentMessage.completedAt,
        updatedAt: timestamp,
      }
    : {
        id: liveMessage.messageId,
        sessionId: liveMessage.sessionId,
        turnId: liveMessage.turnId,
        runId: liveMessage.runId,
        turnMessageIndex: nextTurnMessageIndex(state, liveMessage.turnId),
        role: 'assistant',
        messageType: liveMessage.messageType,
        streamState: liveMessage.streamState,
        displayMode: 'default',
        contentText: liveMessage.contentText,
        payloadJson: liveMessage.payloadJson ?? {},
        createdAt: timestamp,
        updatedAt: timestamp,
        completedAt: isTerminalStreamState(liveMessage.streamState) ? timestamp : null,
      }

  return {
    ...state,
    messageOrder: currentMessage ? state.messageOrder : [...state.messageOrder, liveMessage.messageId],
    messagesById: {
      ...state.messagesById,
      [liveMessage.messageId]: nextMessage,
    },
  }
}

function removePlaceholderAssistantMessage(
  state: ConversationState,
  liveMessage: ConversationLiveMessage
): ConversationState {
  const existing = state.messagesById[liveMessage.messageId]
  if (!existing) {
    return state
  }
  if (existing.streamState !== 'idle' && existing.streamState !== 'streaming') {
    return state
  }
  const { [liveMessage.messageId]: _, ...restMessagesById } = state.messagesById
  return {
    ...state,
    messageOrder: state.messageOrder.filter((id) => id !== liveMessage.messageId),
    messagesById: restMessagesById,
  }
}

export function createEmptyConversationState(sessionId: string | null = null): ConversationState {
  return {
    sessionId,
    lastEventSeq: 0,
    session: null,
    turnOrder: [],
    turnsById: {},
    runsById: {},
    messageOrder: [],
    messagesById: {},
    hasMore: false,
    nextBeforeTurnId: null,
  }
}

export function applyConversationSnapshot(
  previous: ConversationState | undefined,
  snapshot: ConversationSnapshot
): ConversationState {
  const { messageOrder, messagesById: mergedMessagesById } = mergeStreamingMessages(previous, snapshot)
  const runsById = Object.fromEntries(snapshot.runs.map((run) => [run.id, run]))
  const terminalRunIds = new Set(
    snapshot.runs
      .filter((run) => run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled')
      .map((run) => run.id)
  )
  const messagesById = Object.fromEntries(
    Object.entries(mergedMessagesById).map(([messageId, message]) => {
      if (
        message.runId &&
        terminalRunIds.has(message.runId) &&
        (message.streamState === 'idle' || message.streamState === 'streaming')
      ) {
        const run = runsById[message.runId]
        const terminalState: ConversationStreamState = run?.status === 'failed' ? 'failed'
          : run?.status === 'cancelled' ? 'cancelled'
          : 'completed'
        return [messageId, { ...message, streamState: terminalState }]
      }
      return [messageId, message]
    })
  )
  // Preserve prepended history messages (from loadMore) and their associated turns/runs
  // that are not present in the new snapshot
  const incomingSnapshotTurnIds = new Set(snapshot.turns.map((turn) => turn.id))

  let finalMessageOrder = messageOrder
  let finalMessagesById = messagesById
  let finalTurnOrder = snapshot.turns
    .slice()
    .sort((left, right) => left.turnIndex - right.turnIndex)
    .map((turn) => turn.id)
  let finalTurnsById = Object.fromEntries(snapshot.turns.map((turn) => [turn.id, turn]))
  let finalRunsById = runsById

  if (previous) {
    const carriedMessageIds = new Set(messageOrder)
    const prependedIds = previous.messageOrder.filter(
      (id) => !carriedMessageIds.has(id)
    )

    if (prependedIds.length > 0) {
      const prependedMessages = prependedIds
        .map((id) => previous.messagesById[id])
        .filter(Boolean)

      // Find the minimum turn index in the new snapshot
      // Only preserve messages from turns that are OLDER than the snapshot range
      // (i.e., real history from loadMore, not deleted messages)
      const minSnapshotTurnIndex = snapshot.turns.length > 0
        ? Math.min(...snapshot.turns.map((t) => t.turnIndex))
        : Number.MAX_SAFE_INTEGER

      const historyMessages = prependedMessages.filter((m) => {
        const turn = previous.turnsById[m.turnId]
        return turn && turn.turnIndex < minSnapshotTurnIndex
      })

      if (historyMessages.length > 0) {
        // Only process history messages if there are any to preserve
        const snapshotTurnIds = new Set(snapshot.turns.map((t) => t.id))
        const snapshotRunIds = new Set(snapshot.runs.map((r) => r.id))

        const additionalTurns = [...new Set(historyMessages.map((m) => m.turnId).filter((id): id is string => typeof id === 'string'))]
          .filter((id) => !snapshotTurnIds.has(id) && previous.turnsById[id])
          .map((id) => previous.turnsById[id]!)
          .sort((a, b) => a.turnIndex - b.turnIndex)

        const additionalRuns = [...new Set(historyMessages.map((m) => m.runId).filter((id): id is string => typeof id === 'string'))]
          .filter((id) => !snapshotRunIds.has(id) && previous.runsById[id])
          .map((id) => previous.runsById[id]!)

        const allTurns = [...additionalTurns, ...snapshot.turns]
          .sort((a, b) => a.turnIndex - b.turnIndex)
        finalTurnOrder = allTurns.map((t) => t.id)
        finalTurnsById = {
          ...Object.fromEntries(additionalTurns.map((t) => [t.id, t])),
          ...finalTurnsById,
        }

        finalRunsById = {
          ...Object.fromEntries(additionalRuns.map((r) => [r.id, r])),
          ...finalRunsById,
        }

        const historyMessageIds = historyMessages.map((m) => m.id)
        finalMessageOrder = [...historyMessageIds, ...messageOrder]
        finalMessagesById = {
          ...Object.fromEntries(historyMessages.map((m) => [m.id, m])),
          ...messagesById,
        }
      }
    }
  }

  const hasLoadedOlderHistory = previous
    ? previous.turnOrder.some((turnId) => !incomingSnapshotTurnIds.has(turnId))
    : false
  const nextBeforeTurnId = hasLoadedOlderHistory && previous
    ? previous.nextBeforeTurnId
    : snapshot.nextBeforeTurnId

  return {
    sessionId: snapshot.session.id,
    lastEventSeq: snapshot.session.lastEventSeq,
    session: snapshot.session,
    turnOrder: finalTurnOrder,
    turnsById: finalTurnsById,
    runsById: finalRunsById,
    messageOrder: finalMessageOrder,
    messagesById: finalMessagesById,
    hasMore: nextBeforeTurnId !== null,
    nextBeforeTurnId,
  }
}

function applyMessagesTruncated(
  state: ConversationState,
  event: ConversationEvent
): ConversationState {
  const p = event.payloadJson
  const deletedTurnIds = Array.isArray(p.deleted_turn_ids) 
    ? p.deleted_turn_ids.filter((id): id is string => typeof id === 'string')
    : []
  const deletedTurnIdSet = new Set(deletedTurnIds)

  const survivingTurnOrder = state.turnOrder.filter((id) => !deletedTurnIdSet.has(id))
  const survivingTurnsById: Record<string, ConversationState['turnsById'][string]> = {}
  for (const id of survivingTurnOrder) {
    const turn = state.turnsById[id]
    if (turn) survivingTurnsById[id] = turn
  }

  const survivingMessageOrder = state.messageOrder.filter((id) => {
    const msg = state.messagesById[id]
    return msg && !deletedTurnIdSet.has(msg.turnId)
  })
  const survivingMessagesById: Record<string, ConversationMessage> = {}
  for (const id of survivingMessageOrder) {
    const msg = state.messagesById[id]
    if (msg) survivingMessagesById[id] = msg
  }

  const survivingRunsById: Record<string, ConversationRun> = {}
  for (const [id, run] of Object.entries(state.runsById)) {
    if (!deletedTurnIdSet.has(run.turnId)) {
      survivingRunsById[id] = run
    }
  }

  const session = state.session
    ? { ...state.session, activeTurnId: null }
    : null

  return {
    ...state,
    lastEventSeq: event.seq,
    session,
    turnOrder: survivingTurnOrder,
    turnsById: survivingTurnsById,
    runsById: survivingRunsById,
    messageOrder: survivingMessageOrder,
    messagesById: survivingMessagesById,
  }
}

export function applyConversationEvent(state: ConversationState, event: ConversationEvent): ConversationState {
  const currentState = state.sessionId ? state : { ...state, sessionId: event.sessionId }
  if (event.seq <= currentState.lastEventSeq) {
    return currentState
  }

  // 处理子 agent 事件：提取实际事件类型，保留 delegate_call_id
  let actualEvent = event
  if (event.eventType.startsWith('sub_agent:')) {
    const actualEventType = event.eventType.replace('sub_agent:', '')
    actualEvent = {
      ...event,
      eventType: actualEventType,
      // delegate_call_id 已经在事件中，无需额外处理
    }
    // 注意：子 agent 事件会正常处理，delegate_call_id 可用于 UI 层判断是否需要特殊展示
  }

  if (actualEvent.eventType === 'messages.truncated') {
    return applyMessagesTruncated(currentState, actualEvent)
  }

  if (!actualEvent.messageId) {
    if (actualEvent.eventType === 'turn.created') {
      const p = actualEvent.payloadJson
      const turnId = typeof p.turn_id === 'string' ? p.turn_id : (actualEvent.turnId ?? '')
      if (currentState.turnsById[turnId]) {
        return { ...currentState, lastEventSeq: actualEvent.seq }
      }
      const newTurn: ConversationTurn = {
        id: turnId,
        sessionId: actualEvent.sessionId,
        turnIndex: typeof p.turn_index === 'number' ? p.turn_index : 0,
        rootMessageId: typeof p.root_message_id === 'string' ? p.root_message_id : '',
        status: 'running',
        activeRunId: null,
        createdAt: actualEvent.createdAt,
        updatedAt: actualEvent.createdAt,
        completedAt: null,
      }
      return {
        ...currentState,
        lastEventSeq: actualEvent.seq,
        turnOrder: [...currentState.turnOrder, turnId],
        turnsById: { ...currentState.turnsById, [turnId]: newTurn },
      }
    }

    if (actualEvent.runId) {
      const run = currentState.runsById[actualEvent.runId]
      if (actualEvent.eventType === 'run.created') {
        const p = actualEvent.payloadJson
        const newRun: ConversationRun = {
          id: actualEvent.runId,
          sessionId: actualEvent.sessionId,
          turnId: actualEvent.turnId ?? '',
          attemptIndex: typeof p.attempt_index === 'number' ? p.attempt_index : 1,
          status: 'created',
          providerId: typeof p.provider_id === 'string' ? p.provider_id : null,
          modelId: typeof p.model_id === 'string' ? p.model_id : null,
          workspaceRef: typeof p.workspace_ref === 'string' ? p.workspace_ref : null,
          startedAt: null,
          finishedAt: null,
          errorCode: null,
          errorMessage: null,
        }
        return {
          ...currentState,
          lastEventSeq: actualEvent.seq,
          runsById: { ...currentState.runsById, [actualEvent.runId]: newRun },
        }
      }
      if (run) {
        if (actualEvent.eventType === 'run.completed') {
          const finishedAt = typeof actualEvent.payloadJson.finished_at === 'string' ? actualEvent.payloadJson.finished_at : null
          const messagesById: Record<string, ConversationMessage> = Object.fromEntries(
            Object.entries(currentState.messagesById).map(([messageId, message]) => {
              if (
                message.runId === actualEvent.runId &&
                (message.streamState === 'idle' || message.streamState === 'streaming')
              ) {
                return [messageId, {
                  ...message,
                  streamState: 'completed' as const,
                  completedAt: finishedAt ?? message.completedAt,
                  updatedAt: actualEvent.createdAt,
                }]
              }
              return [messageId, message]
            })
          )

          return {
            ...currentState,
            lastEventSeq: actualEvent.seq,
            runsById: {
              ...currentState.runsById,
              [actualEvent.runId]: {
                ...run,
                status: 'completed',
                finishedAt,
              },
            },
            messagesById,
          }
        }
        if (actualEvent.eventType === 'run.failed' || actualEvent.eventType === 'run.cancelled') {
          const terminalState: ConversationStreamState = actualEvent.eventType === 'run.failed' ? 'failed' : 'cancelled'
          const messagesById: Record<string, ConversationMessage> = Object.fromEntries(
            Object.entries(currentState.messagesById).map(([messageId, message]) => {
              if (
                message.runId === actualEvent.runId &&
                (message.streamState === 'idle' || message.streamState === 'streaming')
              ) {
                return [messageId, {
                  ...message,
                  streamState: terminalState,
                  updatedAt: actualEvent.createdAt,
                }]
              }
              return [messageId, message]
            })
          )
          return {
            ...currentState,
            lastEventSeq: actualEvent.seq,
            runsById: {
              ...currentState.runsById,
              [actualEvent.runId]: {
                ...run,
                status: terminalState,
                errorCode: typeof actualEvent.payloadJson.error_code === 'string' ? actualEvent.payloadJson.error_code : null,
                errorMessage: typeof actualEvent.payloadJson.error_message === 'string' ? actualEvent.payloadJson.error_message : null,
              },
            },
            messagesById,
          }
        }
        if (
          actualEvent.eventType === 'run.started' ||
          actualEvent.eventType === 'run.waiting_for_approval' ||
          actualEvent.eventType === 'run.resuming'
        ) {
          const newStatus = actualEvent.eventType === 'run.started' ? 'running'
            : actualEvent.eventType === 'run.waiting_for_approval' ? 'waiting_for_approval'
            : 'resuming'
          return {
            ...currentState,
            lastEventSeq: actualEvent.seq,
            runsById: {
              ...currentState.runsById,
              [actualEvent.runId]: { ...run, status: newStatus },
            },
          }
        }
      }
    }
    return {
      ...currentState,
      lastEventSeq: actualEvent.seq,
    }
  }

  if (actualEvent.eventType === 'message.created') {
    const p = actualEvent.payloadJson
    const messageId = typeof p.message_id === 'string' ? p.message_id : actualEvent.messageId
    if (currentState.messagesById[messageId]) {
      return { ...currentState, lastEventSeq: actualEvent.seq }
    }
    const role = isValidRole(p.role) ? p.role : 'assistant'
    const messageType = isValidMessageType(p.message_type) ? p.message_type : 'tool_trace'
    const turnMessageIndex = typeof p.turn_message_index === 'number' ? p.turn_message_index : 0
    const displayMode = typeof p.display_mode === 'string' ? p.display_mode : 'default'
    const contentText = typeof p.content_text === 'string' ? p.content_text : ''
    const payloadJson = isRecord(p.payload_json) ? p.payload_json : {}

    // 处理附件数据
    const attachments = Array.isArray(p.attachments) ? p.attachments : undefined

    const newMessage: ConversationMessage = {
      id: messageId,
      sessionId: actualEvent.sessionId,
      turnId: actualEvent.turnId ?? currentState.session?.activeTurnId ?? '',
      runId: actualEvent.runId ?? null,
      turnMessageIndex,
      role,
      messageType,
      streamState: 'idle',
      displayMode,
      contentText,
      payloadJson,
      attachments,
      createdAt: actualEvent.createdAt,
      updatedAt: actualEvent.createdAt,
      completedAt: null,
    }
    return {
      ...currentState,
      lastEventSeq: actualEvent.seq,
      messageOrder: [...currentState.messageOrder, messageId],
      messagesById: {
        ...currentState.messagesById,
        [messageId]: newMessage,
      },
    }
  }

  const currentMessage = currentState.messagesById[actualEvent.messageId]
  if (!currentMessage) {
    return {
      ...currentState,
      lastEventSeq: actualEvent.seq,
    }
  }

  if (actualEvent.eventType === 'message.payload_updated') {
    const payloadPatch = actualEvent.payloadJson.payload_json
    const nextPayload = isRecord(payloadPatch) ? payloadPatch : actualEvent.payloadJson

    return {
      ...currentState,
      lastEventSeq: actualEvent.seq,
      messagesById: {
        ...currentState.messagesById,
        [actualEvent.messageId]: {
          ...currentMessage,
          payloadJson: {
            ...currentMessage.payloadJson,
            ...nextPayload,
          },
          updatedAt: actualEvent.createdAt,
        },
      },
    }
  }

  if (actualEvent.eventType === 'message.content_committed') {
    return {
      ...currentState,
      lastEventSeq: actualEvent.seq,
      messagesById: {
        ...currentState.messagesById,
        [actualEvent.messageId]: {
          ...currentMessage,
          contentText: String(actualEvent.payloadJson.content_text ?? ''),
          updatedAt: actualEvent.createdAt,
        },
      },
    }
  }

  if (actualEvent.eventType === 'message.failed') {
    return {
      ...currentState,
      lastEventSeq: actualEvent.seq,
      messagesById: {
        ...currentState.messagesById,
        [actualEvent.messageId]: {
          ...currentMessage,
          streamState: 'failed',
          payloadJson: {
            ...currentMessage.payloadJson,
            ...actualEvent.payloadJson,
          },
          updatedAt: actualEvent.createdAt,
        },
      },
    }
  }

  if (actualEvent.eventType === 'message.completed') {
    return {
      ...currentState,
      lastEventSeq: actualEvent.seq,
      messagesById: {
        ...currentState.messagesById,
        [actualEvent.messageId]: {
          ...currentMessage,
          streamState: 'completed',
          completedAt: actualEvent.createdAt,
          updatedAt: actualEvent.createdAt,
        },
      },
    }
  }

  return {
    ...currentState,
    lastEventSeq: actualEvent.seq,
  }
}

export function prependMessages(
  state: ConversationState,
  messages: ConversationMessage[],
  turns: ConversationTurn[],
  runs: ConversationRun[],
): ConversationState {
  const newMessageIds = messages.map((m) => m.id).filter((id) => !(id in state.messagesById))
  const newMessagesById = Object.fromEntries(
    messages.filter((m) => !(m.id in state.messagesById)).map((m) => [m.id, m])
  )
  const newTurnEntries = turns
    .filter((t) => !(t.id in state.turnsById))
    .sort((a, b) => a.turnIndex - b.turnIndex)
  const mergedTurnOrder = [...state.turnOrder]
  for (const turn of newTurnEntries) {
    let insertPos = mergedTurnOrder.length
    for (let i = 0; i < mergedTurnOrder.length; i++) {
      const existingTurn = state.turnsById[mergedTurnOrder[i]]
      if (existingTurn && existingTurn.turnIndex > turn.turnIndex) {
        insertPos = i
        break
      }
    }
    mergedTurnOrder.splice(insertPos, 0, turn.id)
  }
  const newTurnsById = Object.fromEntries(
    turns.filter((t) => !(t.id in state.turnsById)).map((t) => [t.id, t])
  )
  const newRunsById = Object.fromEntries(
    runs.filter((r) => !(r.id in state.runsById)).map((r) => [r.id, r])
  )
  return {
    ...state,
    messageOrder: [...newMessageIds, ...state.messageOrder],
    messagesById: { ...newMessagesById, ...state.messagesById },
    turnOrder: mergedTurnOrder,
    turnsById: { ...newTurnsById, ...state.turnsById },
    runsById: { ...newRunsById, ...state.runsById },
  }
}

export function applyConversationLiveEvent(
  state: ConversationState,
  liveMessage: ConversationLiveMessage
): ConversationState {
  return upsertLiveAssistantMessage(state, liveMessage)
}

export function applyConversationLiveState(
  state: ConversationState,
  liveMessage: ConversationLiveMessage
): ConversationState {
  if (liveMessage.streamState === 'idle') {
    return removePlaceholderAssistantMessage(state, liveMessage)
  }
  return upsertLiveAssistantMessage(state, liveMessage)
}
