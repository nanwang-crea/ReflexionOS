// 文件功能：会话（conversation）领域的核心类型定义
// 文件描述：定义会话、轮次（turn）、运行（run）、消息（message）、事件（event）等实体的类型，
//          以及后端 DTO（下划线命名）到前端模型（驼峰命名）的转换函数
// 核心逻辑：一次会话（session）包含多个轮次（turn），每个轮次可能有多次运行尝试（run，如失败重试），
//          每次运行产生若干消息（message）；事件（event）是驱动前端实时更新的最小单元，
//          ConversationState 是前端 store 中按 id 索引存储这些实体的规范化（normalized）状态结构

// 会话轮次（turn）的状态：created(已创建) / running(执行中) / completed(已完成) / failed(失败) / cancelled(已取消)
export type ConversationTurnStatus = 'created' | 'running' | 'completed' | 'failed' | 'cancelled'

// 一次运行（run，即某个 turn 下的一次具体执行尝试）的状态，比 turn 状态更细，
// 额外包含 pending(排队中)、waiting_for_approval(等待用户批准)、resuming(恢复执行中)
export type ConversationRunStatus = 'created' | 'pending' | 'running' | 'waiting_for_approval' | 'resuming' | 'completed' | 'failed' | 'cancelled'

// 消息发送者角色：user(用户) / assistant(助手) / tool(工具调用) / system(系统)
type ConversationMessageRole = 'user' | 'assistant' | 'tool' | 'system'

// 消息类型：用户消息 / 助手消息 / 工具调用轨迹 / 系统提示
type ConversationMessageType = 'user_message' | 'assistant_message' | 'tool_trace' | 'system_notice'

// 消息流式传输状态：idle(未开始) / streaming(流式输出中) / completed(已完成) / failed(失败) / cancelled(已取消)
export type ConversationStreamState = 'idle' | 'streaming' | 'completed' | 'failed' | 'cancelled'

// 会话（session）的后端 DTO 结构：字段为后端返回的原始下划线命名（snake_case），
// 需通过 toConversationSession 转换为前端使用的驼峰命名结构 ConversationSession
export interface ConversationSessionDto {
  id: string
  project_id: string
  title: string
  preferred_provider_id?: string | null
  preferred_model_id?: string | null
  agent_mode?: string
  permission_mode?: string
  last_event_seq: number
  active_turn_id: string | null
  created_at: string
  updated_at: string
}

// Agent 工作模式：build(构建/执行模式) / plan(仅规划、不实际执行)
export type AgentMode = 'build' | 'plan'

/**
 * 函数名：isValidAgentMode
 * 入参：
 *   - value (unknown): 待校验的值，通常来自后端 DTO 中的 agent_mode 字段
 * 功能：类型收窄守卫，判断给定值是否为合法的 AgentMode
 * 运行逻辑：直接比较是否等于 'build' 或 'plan'
 * 出参：boolean（类型谓词）- true 表示 value 可安全当作 AgentMode 使用
 */
function isValidAgentMode(value: unknown): value is AgentMode {
  return value === 'build' || value === 'plan'
}

// 权限模式：ask(每次都询问用户) / auto(自动放行) / yolo(完全不询问，风险自负)
export type PermissionMode = 'ask' | 'auto' | 'yolo'

/**
 * 函数名：toConversationSession
 * 入参：
 *   - dto (ConversationSessionDto): 后端返回的原始会话 DTO（下划线命名）
 * 功能：将后端 DTO 转换为前端使用的 ConversationSession（驼峰命名，并对可选/未知字段做兜底）
 * 运行逻辑：
 *   1. 校验 agent_mode 是否合法，非法或缺失时兜底为 'build'
 *   2. 校验 permission_mode 是否为已知取值，非法或缺失时兜底为 'auto'
 *   3. 逐字段从下划线命名映射为驼峰命名，组装成 ConversationSession 对象
 * 出参：ConversationSession - 前端内部使用的会话对象
 */
export function toConversationSession(dto: ConversationSessionDto): ConversationSession {
  const agentMode = isValidAgentMode(dto.agent_mode) ? dto.agent_mode : 'build'
  const permissionMode = dto.permission_mode === 'ask' || dto.permission_mode === 'auto' || dto.permission_mode === 'yolo' ? dto.permission_mode : 'auto'
  return {
    id: dto.id,
    projectId: dto.project_id,
    title: dto.title,
    preferredProviderId: dto.preferred_provider_id ?? undefined,
    preferredModelId: dto.preferred_model_id ?? undefined,
    agentMode,
    permissionMode,
    lastEventSeq: dto.last_event_seq,
    activeTurnId: dto.active_turn_id,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

// 会话（前端模型）：驼峰命名版本，供组件/store 内部使用，由 toConversationSession 从 DTO 转换而来
export interface ConversationSession {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  agentMode?: AgentMode
  permissionMode?: PermissionMode
  lastEventSeq: number
  activeTurnId: string | null // 当前进行中的轮次 id，无进行中轮次时为 null
  createdAt: string
  updatedAt: string
}

// 会话轮次：对应一次“用户提问 -> 助手回复”的完整交互单元，可能包含多次运行尝试
export interface ConversationTurn {
  id: string
  sessionId: string
  turnIndex: number // 轮次在会话中的序号，从 0 或 1 开始递增
  rootMessageId: string // 该轮次的根消息（通常是触发该轮次的用户消息）id
  status: ConversationTurnStatus
  activeRunId: string | null // 当前进行中的运行 id，无进行中运行时为 null
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

// 运行（run）：某个轮次下的一次具体执行尝试（例如失败后自动/手动重试会产生新的 run）
export interface ConversationRun {
  id: string
  sessionId: string
  turnId: string
  attemptIndex: number // 本次运行是该轮次下的第几次尝试，从 0 开始
  status: ConversationRunStatus
  providerId: string | null // 本次运行实际使用的 LLM 提供方 id
  modelId: string | null // 本次运行实际使用的模型 id
  workspaceRef: string | null // 本次运行关联的工作区引用（如 git worktree 路径/分支标识）
  startedAt: string | null
  finishedAt: string | null
  errorCode: string | null // 失败时的错误码，成功或未失败时为 null
  errorMessage: string | null // 失败时的错误信息，成功或未失败时为 null
}

// 会话消息：用户消息、助手回复、工具调用轨迹或系统提示，是会话中展示给用户的基本单元
export interface ConversationMessage {
  id: string
  sessionId: string
  turnId: string
  runId: string | null // 所属运行 id；非运行产生的消息（如系统提示）可为 null
  turnMessageIndex: number // 消息在所属轮次内的序号
  role: ConversationMessageRole
  messageType: ConversationMessageType
  streamState: ConversationStreamState
  displayMode: string // 消息的展示形态（由具体消息类型决定，如纯文本/卡片/工具调用视图等）
  contentText: string
  payloadJson: Record<string, unknown> // 消息的结构化附加数据（如工具调用参数/结果等），随消息类型不同而不同
  attachments?: Array<{
    id: string
    type: string
    mimeType: string
    filePath: string
    fileSize: number
    createdAt: string
  }>
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

// 会话事件：驱动前端实时更新（如 WebSocket 推送）的最小单元，seq 用于保证消费顺序、判断是否有遗漏
export interface ConversationEvent {
  id: string
  sessionId: string
  seq: number // 事件在会话内的全局序号，单调递增，用于对齐 lastEventSeq 判断是否需要补拉
  turnId: string | null
  runId: string | null
  messageId: string | null
  eventType: string // 事件类型标识（如消息创建/状态变更/流式增量等），具体取值由后端定义
  payloadJson: Record<string, unknown>
  createdAt: string
  // 用于标识子 agent 事件，关联到父 agent 的 delegate tool call
  delegate_call_id?: string
}

// 实时消息（流式增量载体）：用于承载消息流式输出过程中的增量片段（delta），而非落库后的完整消息
export interface ConversationLiveMessage {
  sessionId: string
  turnId: string
  runId: string
  messageId: string
  messageType: ConversationMessageType
  contentText: string // 到目前为止已累积拼接的完整文本内容
  streamState: ConversationStreamState
  delta?: string // 本次推送新增的文本片段
  payloadJson?: Record<string, unknown>
}

// 会话快照：一次性拉取的会话数据集合（用于打开会话时的初始加载或翻页加载历史），
// hasMore/nextBeforeTurnId 用于向更早的轮次分页加载
export interface ConversationSnapshot {
  session: ConversationSession
  turns: ConversationTurn[]
  runs: ConversationRun[]
  messages: ConversationMessage[]
  hasMore: boolean
  nextBeforeTurnId: string | null
}

// 会话状态：前端 store 中按 id 规范化（normalized）存储的会话数据结构，
// turnOrder/messageOrder 保存展示顺序，turnsById/runsById/messagesById 按 id 索引存储实体本身
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
