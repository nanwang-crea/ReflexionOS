export type ConversationTurnStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled'

export type ConversationRunStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled'

export type ConversationMessageRole = 'user' | 'assistant' | 'tool' | 'system'

export type ConversationMessageType = 'user_message' | 'assistant_message' | 'tool_trace' | 'system_notice'

export type ConversationStreamState = 'idle' | 'streaming' | 'completed' | 'failed' | 'cancelled'

export interface ConversationSession {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  lastEventSeq: number
  activeTurnId: string | null
  createdAt: string
  updatedAt: string
}

export interface ConversationTurn {
  id: string
  sessionId: string
  turnIndex: number
  rootMessageId: string
  status: ConversationTurnStatus
  activeRunId: string | null
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

export interface ConversationRun {
  id: string
  sessionId: string
  turnId: string
  attemptIndex: number
  status: ConversationRunStatus
  providerId: string | null
  modelId: string | null
  workspaceRef: string | null
  startedAt: string | null
  finishedAt: string | null
  errorCode: string | null
  errorMessage: string | null
}

export interface ConversationMessage {
  id: string
  sessionId: string
  turnId: string
  runId: string | null
  messageIndex: number
  role: ConversationMessageRole
  messageType: ConversationMessageType
  streamState: ConversationStreamState
  displayMode: string
  contentText: string
  payloadJson: Record<string, unknown>
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

export interface ConversationEvent {
  id: string
  sessionId: string
  seq: number
  turnId: string | null
  runId: string | null
  messageId: string | null
  eventType: string
  payloadJson: Record<string, unknown>
  createdAt: string
}

export interface ConversationLiveMessage {
  sessionId: string
  turnId: string
  runId: string
  messageId: string
  messageType: ConversationMessageType
  contentText: string
  streamState: ConversationStreamState
  delta?: string
}

export interface ConversationSnapshot {
  session: ConversationSession
  turns: ConversationTurn[]
  runs: ConversationRun[]
  messages: ConversationMessage[]
}

export interface ConversationState {
  sessionId: string | null
  lastEventSeq: number
  session: ConversationSession | null
  turnOrder: string[]
  turnsById: Record<string, ConversationTurn>
  runsById: Record<string, ConversationRun>
  messageOrder: string[]
  messagesById: Record<string, ConversationMessage>
}
