/**
 * 文件功能：会话（conversation）相关的后端接口封装
 * 文件描述：定义会话快照的后端 DTO（snake_case）类型，并提供 DTO -> 前端领域模型（camelCase）
 *          的转换函数；对外暴露 conversationApi，供页面/store 获取某个会话的完整或分页快照。
 * 核心逻辑：后端返回的字段是 snake_case，需要逐层转换为前端使用的 camelCase 结构
 *          （session/turn/run/message），并将 axios 响应中的 data 字段替换为转换后的结果。
 */
import type { AxiosResponse } from 'axios'
import { apiClient } from '@/services/apiClient'
import type {
  ConversationMessage,
  ConversationRun,
  ConversationSessionDto,
  ConversationSnapshot,
  ConversationTurn,
} from '@/types/conversation'
import { toConversationSession } from '@/types/conversation'

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
  attachments?: Array<{
    id: string
    type: string
    mime_type: string
    file_path: string
    file_size: number
    created_at: string
  }>
  created_at: string
  updated_at: string
  completed_at: string | null
}

interface ConversationSnapshotDto {
  session: ConversationSessionDto
  turns: ConversationTurnDto[]
  runs: ConversationRunDto[]
  messages: ConversationMessageDto[]
  has_more: boolean
  next_before_turn_id: string | null
}

/**
 * 函数名：toConversationTurn
 * 入参：
 *   - dto (ConversationTurnDto): 后端返回的 turn（对话轮次）DTO，字段为 snake_case
 * 功能：将后端 turn DTO 转换为前端使用的 ConversationTurn 领域模型
 * 运行逻辑：逐字段将 snake_case 映射为 camelCase，不做额外校验或默认值处理
 * 出参：ConversationTurn - 转换后的对话轮次对象
 */
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

/**
 * 函数名：toConversationRun
 * 入参：
 *   - dto (ConversationRunDto): 后端返回的 run（一次模型执行）DTO，字段为 snake_case
 * 功能：将后端 run DTO 转换为前端使用的 ConversationRun 领域模型
 * 运行逻辑：逐字段将 snake_case 映射为 camelCase
 * 出参：ConversationRun - 转换后的运行记录对象
 */
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

/**
 * 函数名：toConversationMessage
 * 入参：
 *   - dto (ConversationMessageDto): 后端返回的消息 DTO，字段为 snake_case，可能包含附件列表
 * 功能：将后端消息 DTO 转换为前端使用的 ConversationMessage 领域模型
 * 运行逻辑：逐字段映射为 camelCase；若存在 attachments，逐条转换附件字段（如 mime_type -> mimeType）
 * 出参：ConversationMessage - 转换后的消息对象
 */
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
    attachments: dto.attachments?.map(att => ({
      id: att.id,
      type: att.type,
      mimeType: att.mime_type,
      filePath: att.file_path,
      fileSize: att.file_size,
      createdAt: att.created_at,
    })),
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    completedAt: dto.completed_at,
  }
}

/**
 * 函数名：toConversationSnapshot
 * 入参：
 *   - dto (ConversationSnapshotDto): 后端返回的会话快照 DTO，包含 session/turns/runs/messages 等
 * 功能：将整个会话快照从后端 DTO 转换为前端领域模型
 * 运行逻辑：分别调用 toConversationSession/toConversationTurn/toConversationRun/toConversationMessage
 *          对各子结构做转换，并将分页字段 has_more/next_before_turn_id 转为 camelCase
 * 出参：ConversationSnapshot - 转换后的完整会话快照
 */
function toConversationSnapshot(dto: ConversationSnapshotDto): ConversationSnapshot {
  return {
    session: toConversationSession(dto.session),
    turns: dto.turns.map(toConversationTurn),
    runs: dto.runs.map(toConversationRun),
    messages: dto.messages.map(toConversationMessage),
    hasMore: dto.has_more,
    nextBeforeTurnId: dto.next_before_turn_id ?? null,
  }
}

/**
 * 函数名：mapConversationResponse
 * 入参：
 *   - request (Promise<AxiosResponse<ConversationSnapshotDto>>): 尚未 resolve 的会话快照请求
 * 功能：等待请求完成后，将响应体中的 DTO 数据转换为前端领域模型
 * 运行逻辑：await 原始请求，保留 axios 响应的其他字段（如 status/headers），仅替换 data 字段
 * 出参：Promise<AxiosResponse<ConversationSnapshot>> - data 字段已转换为前端模型的响应
 */
async function mapConversationResponse(
  request: Promise<AxiosResponse<ConversationSnapshotDto>>
): Promise<AxiosResponse<ConversationSnapshot>> {
  const response = await request
  return {
    ...response,
    data: toConversationSnapshot(response.data),
  }
}

/**
 * 函数名：buildSessionConversationPath
 * 入参：
 *   - sessionId (string): 会话 ID
 * 功能：拼接获取指定会话对话内容的后端接口路径
 * 运行逻辑：直接拼接字符串模板，不做编码或校验
 * 出参：string - 形如 /api/sessions/{sessionId}/conversation 的接口路径
 */
function buildSessionConversationPath(sessionId: string) {
  return `/api/sessions/${sessionId}/conversation`
}

// 会话接口封装：对外提供获取会话快照（全量/分页）的方法，内部统一做 DTO -> 领域模型转换
export const conversationApi = {
  // 获取会话最新一页（默认 limit=20）对话快照
  getConversation: (sessionId: string) =>
    mapConversationResponse(apiClient.get<ConversationSnapshotDto>(buildSessionConversationPath(sessionId), { params: { limit: 20 } })),
  // 分页获取会话历史对话快照，支持 limit 和 beforeTurn（用于向前翻页加载更早的轮次）
  getConversationPaginated: (sessionId: string, params: { limit?: number; beforeTurn?: string }) => {
    const queryParams: Record<string, string> = {}
    if (params.limit !== undefined) queryParams.limit = String(params.limit)
    if (params.beforeTurn !== undefined) queryParams.before_turn = params.beforeTurn
    return mapConversationResponse(apiClient.get<ConversationSnapshotDto>(buildSessionConversationPath(sessionId), { params: queryParams }))
  },
}
