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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

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

function nextTurnMessageIndex(state: ConversationState, turnId: string): number {
  const current = Object.values(state.messagesById)
    .filter((message) => message.turnId === turnId)
    .reduce((maxIndex, message) => Math.max(maxIndex, message.turnMessageIndex), 0)
  return current + 1
}

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
        completedAt: null,
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
  return {
    sessionId: snapshot.session.id,
    lastEventSeq: snapshot.session.lastEventSeq,
    session: snapshot.session,
    turnOrder: snapshot.turns
      .slice()
      .sort((left, right) => left.turnIndex - right.turnIndex)
      .map((turn) => turn.id),
    turnsById: Object.fromEntries(snapshot.turns.map((turn) => [turn.id, turn])),
    runsById,
    messageOrder,
    messagesById,
  }
}

function applyMessagesTruncated(
  state: ConversationState,
  event: ConversationEvent
): ConversationState {
  const p = event.payloadJson
  const deletedTurnIds = (p.deleted_turn_ids as string[]) ?? []
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

  if (event.eventType === 'messages.truncated') {
    return applyMessagesTruncated(currentState, event)
  }

  if (!event.messageId) {
    if (event.eventType === 'turn.created') {
      const p = event.payloadJson
      const turnId = (p.turn_id as string) ?? event.turnId ?? ''
      if (currentState.turnsById[turnId]) {
        return { ...currentState, lastEventSeq: event.seq }
      }
      const newTurn: ConversationTurn = {
        id: turnId,
        sessionId: event.sessionId,
        turnIndex: (p.turn_index as number) ?? 0,
        rootMessageId: (p.root_message_id as string) ?? '',
        status: 'running',
        activeRunId: null,
        createdAt: event.createdAt,
        updatedAt: event.createdAt,
        completedAt: null,
      }
      return {
        ...currentState,
        lastEventSeq: event.seq,
        turnOrder: [...currentState.turnOrder, turnId],
        turnsById: { ...currentState.turnsById, [turnId]: newTurn },
      }
    }

    if (event.runId) {
      const run = currentState.runsById[event.runId]
      if (event.eventType === 'run.created') {
        const p = event.payloadJson
        const newRun: ConversationRun = {
          id: event.runId,
          sessionId: event.sessionId,
          turnId: event.turnId ?? '',
          attemptIndex: (p.attempt_index as number) ?? 1,
          status: 'created',
          providerId: (p.provider_id as string | null) ?? null,
          modelId: (p.model_id as string | null) ?? null,
          workspaceRef: (p.workspace_ref as string | null) ?? null,
          startedAt: null,
          finishedAt: null,
          errorCode: null,
          errorMessage: null,
        }
        return {
          ...currentState,
          lastEventSeq: event.seq,
          runsById: { ...currentState.runsById, [event.runId]: newRun },
        }
      }
      if (run) {
        if (event.eventType === 'run.completed') {
          const finishedAt = (event.payloadJson.finished_at as string) ?? null
          const messagesById = Object.fromEntries(
            Object.entries(currentState.messagesById).map(([messageId, message]) => {
              if (
                message.runId === event.runId &&
                (message.streamState === 'idle' || message.streamState === 'streaming')
              ) {
                return [messageId, {
                  ...message,
                  streamState: 'completed',
                  completedAt: finishedAt ?? message.completedAt,
                  updatedAt: event.createdAt,
                }]
              }
              return [messageId, message]
            })
          )

          return {
            ...currentState,
            lastEventSeq: event.seq,
            runsById: {
              ...currentState.runsById,
              [event.runId]: {
                ...run,
                status: 'completed',
                finishedAt,
              },
            },
            messagesById,
          }
        }
        if (event.eventType === 'run.failed' || event.eventType === 'run.cancelled') {
          const terminalState: ConversationStreamState = event.eventType === 'run.failed' ? 'failed' : 'cancelled'
          const messagesById = Object.fromEntries(
            Object.entries(currentState.messagesById).map(([messageId, message]) => {
              if (
                message.runId === event.runId &&
                (message.streamState === 'idle' || message.streamState === 'streaming')
              ) {
                return [messageId, {
                  ...message,
                  streamState: terminalState,
                  updatedAt: event.createdAt,
                }]
              }
              return [messageId, message]
            })
          )
          return {
            ...currentState,
            lastEventSeq: event.seq,
            runsById: {
              ...currentState.runsById,
              [event.runId]: {
                ...run,
                status: terminalState,
                errorCode: (event.payloadJson.error_code as string | null) ?? null,
                errorMessage: (event.payloadJson.error_message as string | null) ?? null,
              },
            },
            messagesById,
          }
        }
        if (
          event.eventType === 'run.started' ||
          event.eventType === 'run.waiting_for_approval' ||
          event.eventType === 'run.resuming'
        ) {
          const newStatus = event.eventType === 'run.started' ? 'running'
            : event.eventType === 'run.waiting_for_approval' ? 'waiting_for_approval'
            : 'resuming'
          return {
            ...currentState,
            lastEventSeq: event.seq,
            runsById: {
              ...currentState.runsById,
              [event.runId]: { ...run, status: newStatus },
            },
          }
        }
      }
    }
    return {
      ...currentState,
      lastEventSeq: event.seq,
    }
  }

  if (event.eventType === 'message.created') {
    const p = event.payloadJson
    const messageId = (p.message_id as string) ?? event.messageId
    if (currentState.messagesById[messageId]) {
      return { ...currentState, lastEventSeq: event.seq }
    }
    const newMessage: ConversationMessage = {
      id: messageId,
      sessionId: event.sessionId,
      turnId: event.turnId ?? currentState.session?.activeTurnId ?? '',
      runId: event.runId ?? null,
      turnMessageIndex: (p.turn_message_index as number) ?? 0,
      role: (p.role as ConversationMessage['role']) ?? 'assistant',
      messageType: (p.message_type as ConversationMessage['messageType']) ?? 'tool_trace',
      streamState: 'idle',
      displayMode: (p.display_mode as string) ?? 'default',
      contentText: (p.content_text as string) ?? '',
      payloadJson: (p.payload_json as Record<string, unknown>) ?? {},
      createdAt: event.createdAt,
      updatedAt: event.createdAt,
      completedAt: null,
    }
    return {
      ...currentState,
      lastEventSeq: event.seq,
      messageOrder: [...currentState.messageOrder, messageId],
      messagesById: {
        ...currentState.messagesById,
        [messageId]: newMessage,
      },
    }
  }

  const currentMessage = currentState.messagesById[event.messageId]
  if (!currentMessage) {
    return {
      ...currentState,
      lastEventSeq: event.seq,
    }
  }

  if (event.eventType === 'message.payload_updated') {
    const payloadPatch = event.payloadJson.payload_json
    const nextPayload = isRecord(payloadPatch) ? payloadPatch : event.payloadJson

    return {
      ...currentState,
      lastEventSeq: event.seq,
      messagesById: {
        ...currentState.messagesById,
        [event.messageId]: {
          ...currentMessage,
          payloadJson: {
            ...currentMessage.payloadJson,
            ...nextPayload,
          },
          updatedAt: event.createdAt,
        },
      },
    }
  }

  if (event.eventType === 'message.content_committed') {
    return {
      ...currentState,
      lastEventSeq: event.seq,
      messagesById: {
        ...currentState.messagesById,
        [event.messageId]: {
          ...currentMessage,
          contentText: String(event.payloadJson.content_text ?? ''),
          updatedAt: event.createdAt,
        },
      },
    }
  }

  if (event.eventType === 'message.failed') {
    return {
      ...currentState,
      lastEventSeq: event.seq,
      messagesById: {
        ...currentState.messagesById,
        [event.messageId]: {
          ...currentMessage,
          streamState: 'failed',
          payloadJson: {
            ...currentMessage.payloadJson,
            ...event.payloadJson,
          },
          updatedAt: event.createdAt,
        },
      },
    }
  }

  if (event.eventType === 'message.completed') {
    return {
      ...currentState,
      lastEventSeq: event.seq,
      messagesById: {
        ...currentState.messagesById,
        [event.messageId]: {
          ...currentMessage,
          streamState: 'completed',
          completedAt: event.createdAt,
          updatedAt: event.createdAt,
        },
      },
    }
  }

  return {
    ...currentState,
    lastEventSeq: event.seq,
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
  return upsertLiveAssistantMessage(state, liveMessage)
}
