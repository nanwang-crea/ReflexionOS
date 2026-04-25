import type {
  ConversationEvent,
  ConversationLiveMessage,
  ConversationMessage,
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
      return leftTurnIndex - rightTurnIndex || left.messageIndex - right.messageIndex
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

function nextMessageIndex(state: ConversationState, turnId: string): number {
  const current = Object.values(state.messagesById)
    .filter((message) => message.turnId === turnId)
    .reduce((maxIndex, message) => Math.max(maxIndex, message.messageIndex), 0)
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
        messageIndex: nextMessageIndex(state, liveMessage.turnId),
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

export function applyConversationEvent(state: ConversationState, event: ConversationEvent): ConversationState {
  const currentState = state.sessionId ? state : { ...state, sessionId: event.sessionId }
  if (event.seq <= currentState.lastEventSeq) {
    return currentState
  }

  if (!event.messageId) {
    return {
      ...currentState,
      lastEventSeq: event.seq,
    }
  }

  const currentMessage = currentState.messagesById[event.messageId]
  if (!currentMessage) {
    return {
      ...currentState,
      lastEventSeq: event.seq,
    }
  }

  if (event.eventType === 'message.delta_appended') {
    const delta = String(event.payloadJson.delta ?? '')
    return {
      ...currentState,
      lastEventSeq: event.seq,
      messagesById: {
        ...currentState.messagesById,
        [event.messageId]: {
          ...currentMessage,
          contentText: `${currentMessage.contentText}${delta}`,
          streamState: 'streaming',
          updatedAt: event.createdAt,
        },
      },
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
