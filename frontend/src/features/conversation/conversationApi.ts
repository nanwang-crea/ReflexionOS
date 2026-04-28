import type { AxiosResponse } from 'axios'
import { apiClient, buildSessionConversationPath } from '@/services/apiClient'
import type {
  ConversationMessage,
  ConversationRun,
  ConversationSession,
  ConversationSnapshot,
  ConversationTurn,
} from '@/types/conversation'

interface ConversationSessionDto {
  id: string
  project_id: string
  title: string
  preferred_provider_id?: string | null
  preferred_model_id?: string | null
  last_event_seq: number
  active_turn_id: string | null
  created_at: string
  updated_at: string
}

interface ConversationTurnDto {
  id: string
  session_id: string
  turn_index: number
  root_message_id: string
  status: ConversationTurn['status']
  active_run_id: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
}

interface ConversationRunDto {
  id: string
  session_id: string
  turn_id: string
  attempt_index: number
  status: ConversationRun['status']
  provider_id: string | null
  model_id: string | null
  workspace_ref: string | null
  started_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
}

interface ConversationMessageDto {
  id: string
  session_id: string
  turn_id: string
  run_id: string | null
  turn_message_index: number
  role: ConversationMessage['role']
  message_type: ConversationMessage['messageType']
  stream_state: ConversationMessage['streamState']
  display_mode: string
  content_text: string
  payload_json: Record<string, unknown>
  created_at: string
  updated_at: string
  completed_at: string | null
}

interface ConversationSnapshotDto {
  session: ConversationSessionDto
  turns: ConversationTurnDto[]
  runs: ConversationRunDto[]
  messages: ConversationMessageDto[]
}

function toConversationSession(dto: ConversationSessionDto): ConversationSession {
  return {
    id: dto.id,
    projectId: dto.project_id,
    title: dto.title,
    preferredProviderId: dto.preferred_provider_id ?? undefined,
    preferredModelId: dto.preferred_model_id ?? undefined,
    lastEventSeq: dto.last_event_seq,
    activeTurnId: dto.active_turn_id,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

function toConversationTurn(dto: ConversationTurnDto): ConversationTurn {
  return {
    id: dto.id,
    sessionId: dto.session_id,
    turnIndex: dto.turn_index,
    rootMessageId: dto.root_message_id,
    status: dto.status,
    activeRunId: dto.active_run_id,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    completedAt: dto.completed_at,
  }
}

function toConversationRun(dto: ConversationRunDto): ConversationRun {
  return {
    id: dto.id,
    sessionId: dto.session_id,
    turnId: dto.turn_id,
    attemptIndex: dto.attempt_index,
    status: dto.status,
    providerId: dto.provider_id,
    modelId: dto.model_id,
    workspaceRef: dto.workspace_ref,
    startedAt: dto.started_at,
    finishedAt: dto.finished_at,
    errorCode: dto.error_code,
    errorMessage: dto.error_message,
  }
}

function toConversationMessage(dto: ConversationMessageDto): ConversationMessage {
  return {
    id: dto.id,
    sessionId: dto.session_id,
    turnId: dto.turn_id,
    runId: dto.run_id,
    turnMessageIndex: dto.turn_message_index,
    role: dto.role,
    messageType: dto.message_type,
    streamState: dto.stream_state,
    displayMode: dto.display_mode,
    contentText: dto.content_text,
    payloadJson: dto.payload_json,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    completedAt: dto.completed_at,
  }
}

function toConversationSnapshot(dto: ConversationSnapshotDto): ConversationSnapshot {
  return {
    session: toConversationSession(dto.session),
    turns: dto.turns.map(toConversationTurn),
    runs: dto.runs.map(toConversationRun),
    messages: dto.messages.map(toConversationMessage),
  }
}

async function mapConversationResponse(
  request: Promise<AxiosResponse<ConversationSnapshotDto>>
): Promise<AxiosResponse<ConversationSnapshot>> {
  const response = await request
  return {
    ...response,
    data: toConversationSnapshot(response.data),
  }
}

export const conversationApi = {
  getConversation: (sessionId: string) =>
    mapConversationResponse(apiClient.get<ConversationSnapshotDto>(buildSessionConversationPath(sessionId))),
}
