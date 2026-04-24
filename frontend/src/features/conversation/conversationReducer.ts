import type {
  ConversationEvent,
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
  _previous: ConversationState | undefined,
  snapshot: ConversationSnapshot
): ConversationState {
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
    messageOrder: buildMessageOrder(snapshot),
    messagesById: Object.fromEntries(snapshot.messages.map((message) => [message.id, message])),
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

  return {
    ...currentState,
    lastEventSeq: event.seq,
  }
}
