import { useCallback, useEffect, useRef, useState, type MutableRefObject } from 'react'
import { ExecutionWebSocket } from '@/services/websocketClient'
import type { ConnectionStatus } from '@/features/workspace/types'

interface ExecutionOverlayBindings {
  activeSessionIdRef: MutableRefObject<string | null>
  currentExecutionIdRef: MutableRefObject<string | null>
  setCurrentExecutionId: (executionId: string | null) => void
  handleConnectionFailure: (message: string) => void
  handleLlmStart: () => void
  handleLlmContent: (content: string) => void
  handleLlmThought: (content: string) => void
  handleToolCall: (data: { tool_name: string; arguments: object; thought: string }) => void
  handleToolStart: (toolName: string) => void
  handleToolResult: (data: {
    tool_name: string
    success: boolean
    output?: string
    error?: string
    duration: number
  }) => void
  handleToolError: (toolName: string, error: string) => void
  handleSummaryStart: () => void
  handleSummaryToken: (token: string) => void
  handleSummaryComplete: (summary: string) => void
  handleExecutionCancelled: () => void
  handleExecutionComplete: (data: { status: string; result: string }) => { failed: boolean }
  handleExecutionError: (error: string) => void
}

interface ExecutionStoreBindings {
  startExecution: (executionId: string, sessionId: string | null) => void
  setThinkingPhase: () => void
  setExecutingPhase: () => void
  setSummarizingPhase: () => void
  completeExecution: () => void
  failExecution: () => void
  cancelExecution: () => void
}

interface UseExecutionWebSocketOptions {
  initialConnectionStatus: ConnectionStatus
  overlay: ExecutionOverlayBindings
  execution: ExecutionStoreBindings
}

export function useExecutionWebSocket({
  initialConnectionStatus,
  overlay,
  execution,
}: UseExecutionWebSocketOptions) {
  const wsRef = useRef<ExecutionWebSocket | null>(null)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(initialConnectionStatus)

  const closeWebSocket = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  const startSocketExecution = useCallback((payload: {
    message: string
    projectId: string
    providerId: string
    modelId: string
  }) => {
    wsRef.current?.startExecution(
      payload.message,
      payload.projectId,
      payload.providerId,
      payload.modelId
    )
  }, [])

  const connectWebSocket = useCallback(async (executionKey: string) => {
    closeWebSocket()

    const ws = new ExecutionWebSocket()

    ws.on('connection:open', () => {
      setConnectionStatus('connected')
    })

    ws.on('connection:closed', (data) => {
      if (data.manuallyClosed) {
        setConnectionStatus('disconnected')
        return
      }

      setConnectionStatus(overlay.currentExecutionIdRef.current ? 'connecting' : 'disconnected')
    })

    ws.on('connection:reconnecting', () => {
      setConnectionStatus('connecting')
    })

    ws.on('connection:failed', () => {
      overlay.handleConnectionFailure('执行连接已断开，请重试。')
      execution.failExecution()
      setConnectionStatus('disconnected')
    })

    ws.on('execution:created', (data) => {
      overlay.setCurrentExecutionId(data.execution_id)
      execution.startExecution(data.execution_id, overlay.activeSessionIdRef.current)
    })

    ws.on('execution:start', (data) => {
      overlay.setCurrentExecutionId(data.execution_id)
      execution.startExecution(data.execution_id, overlay.activeSessionIdRef.current)
    })

    ws.on('llm:start', () => {
      overlay.handleLlmStart()
      execution.setThinkingPhase()
    })

    ws.on('llm:content', (data) => {
      overlay.handleLlmContent(data.content)
      execution.setThinkingPhase()
    })

    ws.on('llm:thought', (data) => {
      overlay.handleLlmThought(data.content)
      execution.setThinkingPhase()
    })

    ws.on('llm:tool_call', (data) => {
      overlay.handleToolCall(data)
      execution.setExecutingPhase()
    })

    ws.on('tool:start', (data) => {
      overlay.handleToolStart(data.tool_name)
      execution.setExecutingPhase()
    })

    ws.on('tool:result', (data) => {
      overlay.handleToolResult(data)
      execution.setExecutingPhase()
    })

    ws.on('tool:error', (data) => {
      overlay.handleToolError(data.tool_name, data.error)
      execution.setExecutingPhase()
    })

    ws.on('summary:start', () => {
      overlay.handleSummaryStart()
      execution.setSummarizingPhase()
    })

    ws.on('summary:token', (data) => {
      overlay.handleSummaryToken(data.token)
      execution.setSummarizingPhase()
    })

    ws.on('summary:complete', (data) => {
      overlay.handleSummaryComplete(data.summary)
    })

    ws.on('execution:cancelled', () => {
      overlay.handleExecutionCancelled()
      execution.cancelExecution()
    })

    ws.on('execution:complete', (data) => {
      const result = overlay.handleExecutionComplete(data)
      if (result.failed) {
        execution.failExecution()
        return
      }

      execution.completeExecution()
    })

    ws.on('execution:error', (data) => {
      overlay.handleExecutionError(data.error)
      execution.failExecution()
    })

    try {
      setConnectionStatus('connecting')
      await ws.connect(executionKey)
      wsRef.current = ws
    } catch (error) {
      console.error('WebSocket connection failed:', error)
      overlay.handleConnectionFailure('连接执行通道失败，请重试。')
      execution.failExecution()
      setConnectionStatus('disconnected')
      throw error
    }
  }, [closeWebSocket, execution, overlay])

  useEffect(() => {
    return () => {
      closeWebSocket()
    }
  }, [closeWebSocket])

  return {
    connectionStatus,
    connectWebSocket,
    startSocketExecution,
    closeWebSocket,
  }
}
