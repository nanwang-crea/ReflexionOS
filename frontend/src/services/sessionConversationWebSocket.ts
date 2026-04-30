import { getSessionConversationWebSocketUrl } from './runtimeConfig'

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

interface PlanStepDto {
  id: number
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'blocked'
  findings: string
}

export interface PlanDto {
  goal: string
  steps: PlanStepDto[]
  current_step_index: number
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
}) {
  return {
    type: 'conversation:start_turn',
    data: {
      content: payload.content,
      provider_id: payload.providerId ?? null,
      model_id: payload.modelId ?? null,
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
  payload: { runId: string; approvalId: string }
) {
  return {
    type,
    data: {
      approval_id: payload.approvalId,
      run_id: payload.runId,
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
    if (message.type === 'conversation:event') {
      this.emit('conversation:event', message.data as SessionConversationEventDto)
      return
    }

    if (message.type === 'conversation:live_event') {
      this.emit('conversation:live_event', message.data as SessionConversationLiveMessageDto)
      return
    }

    if (message.type === 'conversation:live_state') {
      this.emit('conversation:live_state', message.data as SessionConversationLiveMessageDto)
      return
    }

    if (message.type === 'conversation:synced') {
      this.emit('conversation:synced', message.data as ConversationSyncedDto)
      return
    }

    if (message.type === 'conversation:resync_required') {
      this.emit('conversation:resync_required', message.data as ConversationResyncRequiredDto)
      return
    }

    if (message.type === 'conversation:error') {
      this.emit('conversation:error', message.data as ConversationErrorDto)
      return
    }

    if (message.type === 'llm:retry') {
      this.emit('llm:retry', message.data as LlmRetryDto)
      return
    }

    if (message.type === 'plan:updated') {
      this.emit('plan:updated', message.data as PlanDto)
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

  startTurn(payload: { content: string; providerId?: string | null; modelId?: string | null }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildStartTurnMessage(payload)))
    }
  }

  cancelRun(runId: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildCancelRunMessage(runId)))
    }
  }

  approveTool(payload: { runId: string; approvalId: string }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildToolApprovalMessage('conversation:approve_tool', payload)))
    }
  }

  denyTool(payload: { runId: string; approvalId: string }): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(buildToolApprovalMessage('conversation:deny_tool', payload)))
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
