import { getSessionConversationWebSocketUrl } from './runtimeConfig'
import type { PlanStep as PlanStepDto } from '@/types/conversation'

type EventHandler<T = unknown> = (data: T) => void

interface SessionConversationMessageEnvelope {
  type: string
  data: unknown
}

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

interface ConversationSyncedDto {
  session_id: string
  last_event_seq: number
}

interface ConversationResyncRequiredDto {
  session_id: string
  after_seq: number
  reason: string
}

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

// 子 agent 执行事件 DTO（后端通过 sub_agent: 前缀广播）
export interface SubAgentEventDto {
  /** 事件类型：tool:start, tool:result, tool:error, llm:content 等 */
  event_type: string
  /** 关联的父级 delegate 工具调用 ID */
  delegate_call_id?: string
  /** 事件原始数据 */
  payload: Record<string, unknown>
}

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
  // 子 agent 事件：tool:start, tool:result, tool:error, llm:content 等
  'sub_agent:event': SubAgentEventDto
}

function buildSyncMessage(afterSeq: number) {
  return {
    type: 'conversation:sync',
    data: {
      after_seq: afterSeq,
    },
  }
}

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

function buildCancelRunMessage(runId: string) {
  return {
    type: 'conversation:cancel_run',
    data: {
      run_id: runId,
    },
  }
}

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

class SessionConversationWebSocket {
  private ws: WebSocket | null = null
  private handlers: Map<keyof SessionConversationEvents, Set<EventHandler>> = new Map()
  private manuallyClosed = false

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

  private emit<K extends keyof SessionConversationEvents>(event: K, data: SessionConversationEvents[K]) {
    const handlers = this.handlers.get(event)
    if (handlers) {
      handlers.forEach((handler) => handler(data))
    }
  }

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

    // 子 agent 事件：后端以 sub_agent:tool:start, sub_agent:tool:result 等类型发送
    // data 是扁平结构，需要映射为 SubAgentEventDto：event_type + delegate_call_id + payload
    if (type.startsWith('sub_agent:')) {
      const eventType = type.slice('sub_agent:'.length)
      const rawData = (data ?? {}) as Record<string, unknown>
      const { delegate_call_id, ...rest } = rawData
      this.emit('sub_agent:event', {
        event_type: eventType,
        delegate_call_id: delegate_call_id as string | undefined,
        payload: rest,
      } as SubAgentEventDto)
      return
    }
  }

  on<K extends keyof SessionConversationEvents>(event: K, handler: (data: SessionConversationEvents[K]) => void): void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set())
    }

    this.handlers.get(event)?.add(handler as EventHandler)
  }

  off<K extends keyof SessionConversationEvents>(event: K, handler: (data: SessionConversationEvents[K]) => void): void {
    this.handlers.get(event)?.delete(handler as EventHandler)
  }

  sendSync(afterSeq: number): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildSyncMessage(afterSeq)))
    }
  }

  startTurn(payload: { content: string; providerId?: string | null; modelId?: string | null; attachmentIds?: string[] }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildStartTurnMessage(payload)))
    }
  }

  cancelRun(runId: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildCancelRunMessage(runId)))
    }
  }

  approveTool(payload: { runId: string; approvalId: string; decision?: 'allow_once' | 'trust_and_allow'; parentSessionId?: string }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = buildToolApprovalMessage('conversation:approve_tool', payload)
      this.ws.send(JSON.stringify(message))
    }
  }

  denyTool(payload: { runId: string; approvalId: string; parentSessionId?: string }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildToolApprovalMessage('conversation:deny_tool', payload)))
    }
  }

  editAndRerun(payload: { messageId: string; newContent?: string | null; providerId?: string | null; modelId?: string | null }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildEditAndRerunMessage(payload)))
    }
  }

  send(message: { type: string; data: unknown }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  close(): void {
    this.manuallyClosed = true
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.handlers.clear()
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN
  }
}

export { SessionConversationWebSocket }
