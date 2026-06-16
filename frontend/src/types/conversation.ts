export type ConversationTurnStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled'

export type ConversationRunStatus = 'created' | 'pending' | 'running' | 'waiting_for_approval' | 'resuming' | 'completed' | 'failed' | 'cancelled'

type ConversationMessageRole = 'user' | 'assistant' | 'tool' | 'system'

type ConversationMessageType = 'user_message' | 'assistant_message' | 'tool_trace' | 'system_notice'

export type ConversationStreamState = 'idle' | 'streaming' | 'completed' | 'failed' | 'cancelled'

export interface ConversationAttachment {
  id: string
  type: string
  mimeType: string
  filePath: string
  fileSize: number
  createdAt: string
  url?: string
}

export function normalizeConversationAttachment(value: unknown): ConversationAttachment | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  const attachment = value as Record<string, unknown>
  const id = typeof attachment.id === 'string' ? attachment.id : null
  const type = typeof attachment.type === 'string' ? attachment.type : null
  const mimeType = typeof attachment.mimeType === 'string'
    ? attachment.mimeType
    : typeof attachment.mime_type === 'string'
      ? attachment.mime_type
      : null
  const filePath = typeof attachment.filePath === 'string'
    ? attachment.filePath
    : typeof attachment.file_path === 'string'
      ? attachment.file_path
      : null
  const fileSize = typeof attachment.fileSize === 'number'
    ? attachment.fileSize
    : typeof attachment.file_size === 'number'
      ? attachment.file_size
      : null
  const createdAt = typeof attachment.createdAt === 'string'
    ? attachment.createdAt
    : typeof attachment.created_at === 'string'
      ? attachment.created_at
      : null
  const url = typeof attachment.url === 'string' && attachment.url.trim() ? attachment.url : undefined

  if (!id || !type || !mimeType || !filePath || fileSize === null || !createdAt) {
    return null
  }

  return {
    id,
    type,
    mimeType,
    filePath,
    fileSize,
    createdAt,
    url,
  }
}

export interface ConversationSessionDto {
  id: string
  project_id: string
  title: string
  preferred_provider_id?: string | null
  preferred_model_id?: string | null
  agent_mode?: string
  last_event_seq: number
  active_turn_id: string | null
  created_at: string
  updated_at: string
}

export type AgentMode = 'build' | 'plan'

function isValidAgentMode(value: unknown): value is AgentMode {
  return value === 'build' || value === 'plan'
}

export function toConversationSession(dto: ConversationSessionDto): ConversationSession {
  const agentMode = isValidAgentMode(dto.agent_mode) ? dto.agent_mode : 'build'
  return {
    id: dto.id,
    projectId: dto.project_id,
    title: dto.title,
    preferredProviderId: dto.preferred_provider_id ?? undefined,
    preferredModelId: dto.preferred_model_id ?? undefined,
    agentMode,
    lastEventSeq: dto.last_event_seq,
    activeTurnId: dto.active_turn_id,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export interface ConversationSession {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  agentMode?: AgentMode
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
  turnMessageIndex: number
  role: ConversationMessageRole
  messageType: ConversationMessageType
  streamState: ConversationStreamState
  displayMode: string
  contentText: string
  payloadJson: Record<string, unknown>
  attachments?: ConversationAttachment[]
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
  payloadJson?: Record<string, unknown>
}

export interface ConversationSnapshot {
  session: ConversationSession
  turns: ConversationTurn[]
  runs: ConversationRun[]
  messages: ConversationMessage[]
  hasMore: boolean
  nextBeforeTurnId: string | null
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
  hasMore: boolean
  nextBeforeTurnId: string | null
}

export type { Plan, PlanStep } from '@/types/plan'
