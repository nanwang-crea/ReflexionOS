// 文件功能：会话对话 WebSocket 客户端
// 文件描述：封装与后端会话对话 WebSocket 通道的连接、消息收发、事件订阅/取消订阅，
//           覆盖对话事件同步、Turn 发起/取消、工具审批、编辑重跑、子 agent 事件等全部消息类型
// 核心逻辑：SessionConversationWebSocket 类内部维护一个原生 WebSocket 连接与
//           按事件名分组的处理器集合（Map<事件名, Set<回调>>）；
//           connect() 建立连接并把 open/message/error/close 原生事件转译为内部事件；
//           发送类方法（sendSync/startTurn/cancelRun/approveTool/denyTool/editAndRerun/send）
//           负责按约定的消息结构组装 JSON 并在连接就绪时发送；
//           handleMessage 按后端消息 type 字段路由到 emit，转发给通过 on() 订阅的回调；
//           sub_agent: 前缀的消息类型是子 agent 执行事件的通用路由，事件类型和 payload
//           从消息体中动态解析出来，而非逐一定义消息类型
import { getSessionConversationWebSocketUrl } from './runtimeConfig'
import type { PlanStep as PlanStepDto } from '@/types/conversation'

// 事件处理器的通用类型：接收一个数据参数，无返回值
type EventHandler<T = unknown> = (data: T) => void

// 服务端下发消息的通用信封结构：type 标识消息类型，data 为该类型对应的负载
interface SessionConversationMessageEnvelope {
  type: string
  data: unknown
}

// 会话对话中的持久化事件（如消息创建等），对应后端持久存储的事件记录
export interface SessionConversationEventDto {
  id: string
  session_id: string
  seq: number
  turn_id: string | null
  run_id: string | null
  message_id: string | null
  event_type: string
  payload_json: Record<string, unknown>
  created_at: string
}

// 会话对话中的实时流式消息（尚未落库/正在流式输出的消息片段）
export interface SessionConversationLiveMessageDto {
  session_id: string
  turn_id: string
  run_id: string
  message_id: string
  message_type: string
  content_text: string
  stream_state: string
  delta?: string
  payload_json?: Record<string, unknown>
}

// 服务端确认事件流已同步完成的通知：告知客户端已同步到的最新事件序号
interface ConversationSyncedDto {
  session_id: string
  last_event_seq: number
}

// 服务端要求客户端重新同步事件流的通知（如序号跳跃/断线时长过久等场景）
interface ConversationResyncRequiredDto {
  session_id: string
  after_seq: number
  reason: string
}

// 服务端返回的对话级错误信息
interface ConversationErrorDto {
  code: string
  message: string
}

export interface LlmRetryDto {
  error_type: string
  attempt: number
  max_retries: number
  delay: number
  message: string
}

export interface PlanDto {
  goal: string
  steps: PlanStepDto[]
}

export interface SessionTitleUpdatedDto {
  session_id: string
  title: string
}

export interface SessionModeChangedDto {
  session_id: string
  mode: string
}

export interface SessionPermissionModeChangedDto {
  session_id: string
  mode: string
}

// 子 agent 执行事件 DTO（后端通过 sub_agent: 前缀广播）
export interface SubAgentEventDto {
  /** 事件类型：tool:start, tool:result, tool:error, llm:content 等 */
  event_type: string
  /** 关联的父级 delegate 工具调用 ID */
  delegate_call_id?: string
  /** 事件原始数据 */
  payload: Record<string, unknown>
}

// 本客户端对外暴露的内部事件表：key 为事件名，value 为该事件回调收到的数据类型
// 既包含连接生命周期事件（connection:*），也包含从服务端消息转译而来的对话/计划/子agent事件
interface SessionConversationEvents {
  'connection:open': { sessionId: string }
  'connection:error': { sessionId: string; error: unknown }
  'connection:closed': {
    sessionId: string
    code: number
    reason: string
    wasClean: boolean
    manuallyClosed: boolean
  }
  'conversation:event': SessionConversationEventDto
  'conversation:live_event': SessionConversationLiveMessageDto
  'conversation:live_state': SessionConversationLiveMessageDto
  'conversation:resync_required': ConversationResyncRequiredDto
  'conversation:synced': ConversationSyncedDto
  'conversation:error': ConversationErrorDto
  'llm:retry': LlmRetryDto
  'plan:updated': PlanDto
  'plan:discarded': { path: string; goal: string }
  'plan:recovered': { path: string; goal: string }
  'session:title_updated': SessionTitleUpdatedDto
  'session:mode_changed': SessionModeChangedDto
  'session:permission_mode_changed': SessionPermissionModeChangedDto
  // 子 agent 事件：tool:start, tool:result, tool:error, llm:content 等
  'sub_agent:event': SubAgentEventDto
}

/**
 * 函数名：buildSyncMessage
 * 入参：
 *   - afterSeq (number): 客户端已知的最新事件序号
 * 功能：构造向服务端请求同步事件流的消息体
 * 运行逻辑：按约定信封结构包装 after_seq 字段
 * 出参：{ type: string, data: { after_seq: number } } - 可直接 JSON.stringify 后发送的消息对象
 */
function buildSyncMessage(afterSeq: number) {
  return {
    type: 'conversation:sync',
    data: {
      after_seq: afterSeq,
    },
  }
}

/**
 * 函数名：buildStartTurnMessage
 * 入参：
 *   - payload (object): content（用户输入内容）、providerId/modelId（可选的模型提供方与
 *     模型标识）、attachmentIds（可选的附件 ID 列表）
 * 功能：构造发起新一轮对话（Turn）的消息体
 * 运行逻辑：将驼峰字段名转换为后端约定的下划线字段名，可选字段缺省时分别以 null / 空数组兜底
 * 出参：消息对象，供发送前 JSON.stringify
 */
function buildStartTurnMessage(payload: {
  content: string
  providerId?: string | null
  modelId?: string | null
  attachmentIds?: string[]
}) {
  return {
    type: 'conversation:start_turn',
    data: {
      content: payload.content,
      provider_id: payload.providerId ?? null,
      model_id: payload.modelId ?? null,
      attachment_ids: payload.attachmentIds ?? [],
    },
  }
}

/**
 * 函数名：buildCancelRunMessage
 * 入参：
 *   - runId (string): 需要取消的运行（Run）ID
 * 功能：构造取消当前运行的消息体
 * 运行逻辑：按约定信封结构包装 run_id 字段
 * 出参：消息对象，供发送前 JSON.stringify
 */
function buildCancelRunMessage(runId: string) {
  return {
    type: 'conversation:cancel_run',
    data: {
      run_id: runId,
    },
  }
}

/**
 * 函数名：buildToolApprovalMessage
 * 入参：
 *   - type ('conversation:approve_tool' | 'conversation:deny_tool'): 消息类型，区分批准/拒绝
 *   - payload (object): runId（运行ID）、approvalId（审批请求ID）、
 *     decision（可选，'allow_once' 单次允许或 'trust_and_allow' 信任并允许）、
 *     parentSessionId（可选，子 agent 场景下的父会话 ID）
 * 功能：构造工具调用审批（批准或拒绝）的消息体，供 approveTool/denyTool 共用
 * 运行逻辑：先组装必填的 approval_id、run_id；decision 与 parent_session_id 仅在提供时才写入，
 *           避免向后端发送多余的 undefined 字段
 * 出参：{ type, data } - 消息对象，供发送前 JSON.stringify
 */
function buildToolApprovalMessage(
  type: 'conversation:approve_tool' | 'conversation:deny_tool',
  payload: { runId: string; approvalId: string; decision?: 'allow_once' | 'trust_and_allow'; parentSessionId?: string }
) {
  const data: Record<string, string> = {
    approval_id: payload.approvalId,
    run_id: payload.runId,
  }
  if (payload.decision) {
    data.decision = payload.decision
  }
  if (payload.parentSessionId) {
    data.parent_session_id = payload.parentSessionId
  }
  return { type, data }
}

/**
 * 函数名：buildEditAndRerunMessage
 * 入参：
 *   - payload (object): messageId（待编辑消息ID）、newContent（可选新内容）、
 *     providerId/modelId（可选，重跑时指定的模型提供方与模型）
 * 功能：构造“编辑消息并重新运行”的消息体
 * 运行逻辑：将驼峰字段名转换为后端约定的下划线字段名，可选字段缺省时以 null 兜底
 * 出参：消息对象，供发送前 JSON.stringify
 */
function buildEditAndRerunMessage(payload: {
  messageId: string
  newContent?: string | null
  providerId?: string | null
  modelId?: string | null
}) {
  return {
    type: 'conversation:edit_and_rerun',
    data: {
      message_id: payload.messageId,
      new_content: payload.newContent ?? null,
      provider_id: payload.providerId ?? null,
      model_id: payload.modelId ?? null,
    },
  }
}

// SessionConversationWebSocket：会话对话 WebSocket 客户端主类
// 维护单条 WebSocket 连接及按事件名分组的回调集合，对外提供连接管理、消息发送与事件订阅能力
class SessionConversationWebSocket {
  private ws: WebSocket | null = null
  private handlers: Map<keyof SessionConversationEvents, Set<EventHandler>> = new Map()
  private manuallyClosed = false

  /**
   * 函数名：connect
   * 入参：
   *   - sessionId (string): 要连接的会话 ID
   * 功能：建立到指定会话的 WebSocket 连接，并将原生 WebSocket 事件转译为内部事件
   * 运行逻辑：
   *   1. 重置手动关闭标志，按 sessionId 计算连接地址并创建原生 WebSocket
   *   2. onopen：触发 'connection:open' 内部事件，并在首次触发时 resolve 外层 Promise
   *   3. onmessage：JSON 解析消息体后交给 handleMessage 路由，解析失败仅打印日志不中断连接
   *   4. onerror：触发 'connection:error'，若连接尚未 settle 则 reject 外层 Promise
   *   5. onclose：清空 ws 引用并触发 'connection:closed'（携带关闭码/原因/是否手动关闭等信息），
   *      若连接从未成功打开过则 reject 外层 Promise
   *   6. settled 标志确保 resolve/reject 只会被调用一次
   * 出参：Promise<void> - 连接成功打开时 resolve，打开失败或未打开即关闭时 reject
   */
  connect(sessionId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.manuallyClosed = false
      const wsUrl = getSessionConversationWebSocketUrl(sessionId)
      let settled = false

      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        this.emit('connection:open', { sessionId })
        if (!settled) {
          settled = true
          resolve()
        }
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('[ConversationWS] Parse error:', error)
        }
      }

      this.ws.onerror = (error) => {
        this.emit('connection:error', { sessionId, error })
        if (!settled) {
          settled = true
          reject(error)
        }
      }

      this.ws.onclose = (event) => {
        this.ws = null
        this.emit('connection:closed', {
          sessionId,
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
          manuallyClosed: this.manuallyClosed,
        })
        if (!settled) {
          settled = true
          reject(new Error('WebSocket closed before opening'))
        }
      }
    })
  }

  /**
   * 函数名：emit
   * 入参：
   *   - event (K): 内部事件名
   *   - data (SessionConversationEvents[K]): 该事件对应的数据
   * 功能：将指定事件的数据分发给所有已订阅的处理器
   * 运行逻辑：查找该事件名对应的处理器集合，存在则逐一调用；不存在则什么都不做
   * 出参：无
   */
  private emit<K extends keyof SessionConversationEvents>(event: K, data: SessionConversationEvents[K]) {
    const handlers = this.handlers.get(event)
    if (handlers) {
      handlers.forEach((handler) => handler(data))
    }
  }

  /**
   * 函数名：handleMessage
   * 入参：
   *   - message (SessionConversationMessageEnvelope): 服务端下发的原始消息（type + data）
   * 功能：根据消息 type 字段将其路由到对应的内部事件
   * 运行逻辑：
   *   1. 对每种已知的固定消息类型（conversation:*、llm:retry、plan:*、session:*），
   *      直接将 data 断言为对应 DTO 类型并 emit，然后 return
   *   2. 对 sub_agent: 前缀的消息类型（后端以 sub_agent:tool:start 等动态类型广播），
   *      截取前缀后的部分作为 event_type，并从扁平的 data 中拆出 delegate_call_id
   *      （非字符串时置为 undefined），其余字段作为 payload，统一 emit 为 'sub_agent:event'
   *   3. 未匹配任何已知类型的消息会被静默忽略
   * 出参：无
   */
  private handleMessage(message: SessionConversationMessageEnvelope) {
    const { type, data } = message

    if (type === 'conversation:event') {
      this.emit('conversation:event', data as SessionConversationEventDto)
      return
    }

    if (type === 'conversation:live_event') {
      this.emit('conversation:live_event', data as SessionConversationLiveMessageDto)
      return
    }

    if (type === 'conversation:live_state') {
      this.emit('conversation:live_state', data as SessionConversationLiveMessageDto)
      return
    }

    if (type === 'conversation:synced') {
      this.emit('conversation:synced', data as ConversationSyncedDto)
      return
    }

    if (type === 'conversation:resync_required') {
      this.emit('conversation:resync_required', data as ConversationResyncRequiredDto)
      return
    }

    if (type === 'conversation:error') {
      this.emit('conversation:error', data as ConversationErrorDto)
      return
    }

    if (type === 'llm:retry') {
      this.emit('llm:retry', data as LlmRetryDto)
      return
    }

    if (type === 'plan:updated') {
      this.emit('plan:updated', data as PlanDto)
      return
    }

    if (type === 'plan:discarded') {
      this.emit('plan:discarded', data as { path: string; goal: string })
      return
    }

    if (type === 'plan:recovered') {
      this.emit('plan:recovered', data as { path: string; goal: string })
      return
    }

    if (type === 'session:title_updated') {
      this.emit('session:title_updated', data as SessionTitleUpdatedDto)
      return
    }

    if (type === 'session:mode_changed') {
      this.emit('session:mode_changed', data as SessionModeChangedDto)
      return
    }

    if (type === 'session:permission_mode_changed') {
      this.emit('session:permission_mode_changed', data as SessionPermissionModeChangedDto)
      return
    }

    // 子 agent 事件：后端以 sub_agent:tool:start, sub_agent:tool:result 等类型发送
    // data 是扁平结构，需要映射为 SubAgentEventDto：event_type + delegate_call_id + payload
    if (type.startsWith('sub_agent:')) {
      const eventType = type.slice('sub_agent:'.length)
      const rawData = (data ?? {}) as Record<string, unknown>
      const { delegate_call_id, ...rest } = rawData
      this.emit('sub_agent:event', {
        event_type: eventType,
        delegate_call_id: typeof delegate_call_id === 'string' ? delegate_call_id : undefined,
        payload: rest,
      })
      return
    }
  }

  /**
   * 函数名：on
   * 入参：
   *   - event (K): 要订阅的内部事件名
   *   - handler ((data: SessionConversationEvents[K]) => void): 事件触发时的回调
   * 功能：订阅指定的内部事件
   * 运行逻辑：若该事件名尚无处理器集合则先创建一个空 Set，再将回调加入集合
   * 出参：无
   */
  on<K extends keyof SessionConversationEvents>(event: K, handler: (data: SessionConversationEvents[K]) => void): void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set())
    }

    this.handlers.get(event)?.add(handler as EventHandler)
  }

  /**
   * 函数名：off
   * 入参：
   *   - event (K): 要取消订阅的内部事件名
   *   - handler ((data: SessionConversationEvents[K]) => void): 之前通过 on 注册的回调
   * 功能：取消订阅指定的内部事件
   * 运行逻辑：从该事件名对应的处理器集合中删除该回调（若集合不存在则安全忽略）
   * 出参：无
   */
  off<K extends keyof SessionConversationEvents>(event: K, handler: (data: SessionConversationEvents[K]) => void): void {
    this.handlers.get(event)?.delete(handler as EventHandler)
  }

  /**
   * 函数名：sendSync
   * 入参：
   *   - afterSeq (number): 客户端已知的最新事件序号
   * 功能：向服务端请求同步指定序号之后的事件
   * 运行逻辑：仅当连接存在且处于 OPEN 状态时才发送，否则静默跳过
   * 出参：无
   */
  sendSync(afterSeq: number): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildSyncMessage(afterSeq)))
    }
  }

  /**
   * 函数名：startTurn
   * 入参：
   *   - payload (object): content、providerId、modelId、attachmentIds（详见 buildStartTurnMessage）
   * 功能：发起新一轮对话（Turn）
   * 运行逻辑：仅当连接处于 OPEN 状态时，构造并发送开始对话消息
   * 出参：无
   */
  startTurn(payload: { content: string; providerId?: string | null; modelId?: string | null; attachmentIds?: string[] }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildStartTurnMessage(payload)))
    }
  }

  /**
   * 函数名：cancelRun
   * 入参：
   *   - runId (string): 要取消的运行 ID
   * 功能：取消指定的运行
   * 运行逻辑：仅当连接处于 OPEN 状态时，构造并发送取消运行消息
   * 出参：无
   */
  cancelRun(runId: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildCancelRunMessage(runId)))
    }
  }

  /**
   * 函数名：approveTool
   * 入参：
   *   - payload (object): runId、approvalId、decision（可选）、parentSessionId（可选）
   * 功能：批准一次工具调用审批请求
   * 运行逻辑：仅当连接处于 OPEN 状态时，构造 'conversation:approve_tool' 类型消息并发送
   * 出参：无
   */
  approveTool(payload: { runId: string; approvalId: string; decision?: 'allow_once' | 'trust_and_allow'; parentSessionId?: string }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = buildToolApprovalMessage('conversation:approve_tool', payload)
      this.ws.send(JSON.stringify(message))
    }
  }

  /**
   * 函数名：denyTool
   * 入参：
   *   - payload (object): runId、approvalId、parentSessionId（可选）
   * 功能：拒绝一次工具调用审批请求
   * 运行逻辑：仅当连接处于 OPEN 状态时，构造 'conversation:deny_tool' 类型消息并发送
   * 出参：无
   */
  denyTool(payload: { runId: string; approvalId: string; parentSessionId?: string }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildToolApprovalMessage('conversation:deny_tool', payload)))
    }
  }

  /**
   * 函数名：editAndRerun
   * 入参：
   *   - payload (object): messageId、newContent（可选）、providerId（可选）、modelId（可选）
   * 功能：编辑指定消息内容并重新运行
   * 运行逻辑：仅当连接处于 OPEN 状态时，构造并发送编辑重跑消息
   * 出参：无
   */
  editAndRerun(payload: { messageId: string; newContent?: string | null; providerId?: string | null; modelId?: string | null }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildEditAndRerunMessage(payload)))
    }
  }

  /**
   * 函数名：send
   * 入参：
   *   - message ({ type: string, data: unknown }): 任意结构的消息对象
   * 功能：通用消息发送接口，供未封装专用方法的消息类型使用
   * 运行逻辑：仅当连接处于 OPEN 状态时，将消息 JSON 序列化后发送
   * 出参：无
   */
  send(message: { type: string; data: unknown }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  /**
   * 函数名：close
   * 入参：无
   * 功能：主动关闭当前 WebSocket 连接并清理内部状态
   * 运行逻辑：标记为手动关闭（避免 onclose 中的重连/错误提示逻辑误判为异常断线），
   *           关闭并释放原生 WebSocket 引用，清空所有已订阅的事件处理器
   * 出参：无
   */
  close(): void {
    this.manuallyClosed = true
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.handlers.clear()
  }

  /**
   * 函数名：isConnected
   * 入参：无
   * 功能：判断当前 WebSocket 连接是否处于已建立（OPEN）状态
   * 运行逻辑：检查 ws 引用非空且其 readyState 为 OPEN
   * 出参：boolean - true 表示连接可用
   */
  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN
  }
}

export { SessionConversationWebSocket }
