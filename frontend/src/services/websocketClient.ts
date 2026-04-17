type EventHandler = (data: any) => void

interface ExecutionEvents {
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

class ExecutionWebSocket {
  private ws: WebSocket | null = null
  private handlers: Map<string, Set<EventHandler>> = new Map()
  private executionId: string = ''
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private manuallyClosed = false

  connect(executionId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.executionId = executionId
      this.manuallyClosed = false
      const wsUrl = `ws://127.0.0.1:8000/ws/execution/${executionId}`
      
      this.ws = new WebSocket(wsUrl)
      
      this.ws.onopen = () => {
        console.log('[WS] Connected:', executionId)
        this.reconnectAttempts = 0
        resolve()
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
        reject(error)
      }
      
      this.ws.onclose = () => {
        console.log('[WS] Disconnected')
        if (!this.manuallyClosed) {
          this.handleReconnect()
        }
      }
    })
  }

  private handleMessage(message: { type: string; data: any; timestamp: string }) {
    const handlers = this.handlers.get(message.type)
    if (handlers) {
      handlers.forEach(handler => handler(message.data))
    }
    
    // Also emit to '*' wildcard handlers
    const wildcardHandlers = this.handlers.get('*')
    if (wildcardHandlers) {
      wildcardHandlers.forEach(handler => handler(message))
    }
  }

  private handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`[WS] Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
      
      setTimeout(() => {
        this.connect(this.executionId).catch(console.error)
      }, this.reconnectDelay * this.reconnectAttempts)
    }
  }

  on<K extends keyof ExecutionEvents>(event: K, handler: (data: ExecutionEvents[K]) => void): void
  on(event: '*', handler: (message: any) => void): void
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

  startExecution(task: string, projectId: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'start',
        data: { task, project_id: projectId }
      }))
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
export type { ExecutionEvents }
