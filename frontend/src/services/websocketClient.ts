import { getExecutionWebSocketUrl } from './runtimeConfig'

type EventHandler<T = unknown> = (data: T) => void

interface ExecutionMessageEnvelope {
  type: string
  data: unknown
  timestamp?: string
}

interface ExecutionEvents {
  '*': ExecutionMessageEnvelope
  'connection:open': { executionId: string }
  'connection:error': { executionId: string; error: unknown }
  'connection:closed': {
    executionId: string
    code: number
    reason: string
    wasClean: boolean
    manuallyClosed: boolean
  }
  'connection:reconnecting': { executionId: string; attempt: number; maxAttempts: number }
  'connection:failed': { executionId: string; attempts: number }
  'execution:start': { execution_id: string; task: string }
  'execution:created': { execution_id: string; task: string; status: string }
  'llm:start': {}
  'llm:content': { content: string }
  'llm:thought': { content: string }
  'llm:tool_call': { tool_name: string; arguments: object; thought: string }
  'tool:start': { tool_name: string; arguments: object; step_number: number }
  'tool:result': { tool_name: string; success: boolean; output?: string; error?: string; duration: number }
  'tool:error': { tool_name: string; error: string }
  'summary:start': {}
  'summary:token': { token: string }
  'summary:complete': { summary: string }
  'execution:cancelled': { status: string; result: string; total_steps: number; duration?: number }
  'execution:complete': { status: string; result: string; total_steps: number; duration: number }
  'execution:error': { error: string }
}

function buildExecutionStartMessage(
  task: string,
  projectPath: string,
  providerId?: string,
  modelId?: string
) {
  return {
    type: 'start',
    data: {
      task,
      project_path: projectPath,
      provider_id: providerId,
      model_id: modelId,
    },
  }
}

class ExecutionWebSocket {
  private ws: WebSocket | null = null
  private handlers: Map<string, Set<EventHandler>> = new Map()
  private executionId: string = ''
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private manuallyClosed = false
  private hasConnectedOnce = false
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null

  connect(executionId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.executionId = executionId
      this.manuallyClosed = false
      const wsUrl = getExecutionWebSocketUrl(executionId)
      let settled = false

      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        console.log('[WS] Connected:', executionId)
        this.reconnectAttempts = 0
        this.hasConnectedOnce = true
        this.emit('connection:open', { executionId })

        if (!settled) {
          settled = true
          resolve()
        }
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (e) {
          console.error('[WS] Parse error:', e)
        }
      }

      this.ws.onerror = (error) => {
        console.error('[WS] Error:', error)
        this.emit('connection:error', { executionId, error })

        if (!settled && !this.hasConnectedOnce) {
          settled = true
          reject(error)
        }
      }

      this.ws.onclose = (event) => {
        console.log('[WS] Disconnected')
        this.ws = null
        this.emit('connection:closed', {
          executionId,
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
          manuallyClosed: this.manuallyClosed,
        })

        if (!settled && !this.hasConnectedOnce) {
          settled = true
          reject(new Error('WebSocket closed before opening'))
        }

        if (!this.manuallyClosed && this.hasConnectedOnce) {
          this.handleReconnect()
        }
      }
    })
  }

  private emit<K extends keyof ExecutionEvents>(event: K, data: ExecutionEvents[K]) {
    const handlers = this.handlers.get(event)
    if (handlers) {
      handlers.forEach((handler) => handler(data))
    }
  }

  private handleMessage(message: ExecutionMessageEnvelope) {
    const handlers = this.handlers.get(message.type)
    if (handlers) {
      handlers.forEach(handler => handler(message.data))
    }

    const wildcardHandlers = this.handlers.get('*')
    if (wildcardHandlers) {
      wildcardHandlers.forEach(handler => handler(message))
    }
  }

  private handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`[WS] Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)

      this.emit('connection:reconnecting', {
        executionId: this.executionId,
        attempt: this.reconnectAttempts,
        maxAttempts: this.maxReconnectAttempts,
      })

      this.reconnectTimeout = setTimeout(() => {
        this.connect(this.executionId).catch(console.error)
      }, this.reconnectDelay * this.reconnectAttempts)
      return
    }

    this.emit('connection:failed', {
      executionId: this.executionId,
      attempts: this.reconnectAttempts,
    })
  }

  on<K extends keyof ExecutionEvents>(event: K, handler: (data: ExecutionEvents[K]) => void): void
  on(event: string, handler: EventHandler): void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set())
    }
    this.handlers.get(event)!.add(handler)
  }

  off(event: string, handler: EventHandler): void {
    const handlers = this.handlers.get(event)
    if (handlers) {
      handlers.delete(handler)
    }
  }

  startExecution(task: string, projectPath: string, providerId?: string, modelId?: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(
        buildExecutionStartMessage(task, projectPath, providerId, modelId)
      ))
    }
  }

  pause(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'pause' }))
    }
  }

  resume(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'resume' }))
    }
  }

  stop(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'stop' }))
    }
  }

  ping(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }))
    }
  }

  close(): void {
    this.manuallyClosed = true
    this.hasConnectedOnce = false
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
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

export { ExecutionWebSocket }
