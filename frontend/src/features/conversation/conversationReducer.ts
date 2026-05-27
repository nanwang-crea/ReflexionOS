import type {
  ConversationEvent,
  ConversationLiveMessage,
  ConversationMessage,
  ConversationRun,
  ConversationSnapshot,
  ConversationState,
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
        payloadJson: {},
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
  const { messageOrder, messagesById } = mergeStreamingMessages(previous, snapshot)
  return {
    sessionId: snapshot.session.id,
    lastEventSeq: snapshot.session.lastEventSeq,
    session: snapshot.session,
    turnOrder: snapshot.turns
      .slice()
      .sort((left, right) => left.turnIndex - right.turnIndex)
      .map((turn) => turn.id),
    turnsById: Object.fromEntries(snapshot.turns.map((turn) => [turn.id, turn])),
    runsById: Object.fromEntries(snapshot.runs.map((run) => [run.id, run])),
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
    if (event.runId) {
      const run = currentState.runsById[event.runId]
      if (run) {
        if (event.eventType === 'run.completed') {
          return {
            ...currentState,
            lastEventSeq: event.seq,
            runsById: {
              ...currentState.runsById,
              [event.runId]: {
                ...run,
                status: 'completed',
                finishedAt: (event.payloadJson.finished_at as string) ?? null,
              },
            },
          }
        }
        if (event.eventType === 'run.failed' || event.eventType === 'run.cancelled') {
          return {
            ...currentState,
            lastEventSeq: event.seq,
            runsById: {
              ...currentState.runsById,
              [event.runId]: {
                ...run,
                status: event.eventType === 'run.failed' ? 'failed' : 'cancelled',
                errorCode: (event.payloadJson.error_code as string | null) ?? null,
                errorMessage: (event.payloadJson.error_message as string | null) ?? null,
              },
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
