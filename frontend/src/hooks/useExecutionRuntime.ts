import { useCallback, useEffect } from 'react'
import { agentApi } from '@/services/apiClient'
import { shouldResetOverlayForSessionChange } from './executionOverlayState'
import { useExecutionStore } from '@/stores/executionStore'
import { useExecutionOverlay } from './useExecutionOverlay'
import { useExecutionWebSocket } from './useExecutionWebSocket'
import type { ConnectionStatus } from '@/features/workspace/types'

export function useExecutionRuntime(
  currentSessionId: string | null,
  initialConnectionStatus: ConnectionStatus = 'disconnected'
) {
  const {
    phase,
    startExecution,
    setStatus,
    setPhase,
    setCanCancel,
    setThinkingPhase,
    setExecutingPhase,
    setSummarizingPhase,
    startCancelling,
    completeExecution,
    failExecution,
    cancelExecution,
    resetExecution,
  } = useExecutionStore()

  const overlay = useExecutionOverlay()
  const {
    connectionStatus,
    connectWebSocket,
    startSocketExecution,
    closeWebSocket,
  } = useExecutionWebSocket({
    initialConnectionStatus,
    overlay,
    execution: {
      startExecution,
      setThinkingPhase,
      setExecutingPhase,
      setSummarizingPhase,
      completeExecution,
      failExecution,
      cancelExecution,
    },
  })

  const startExecutionRun = useCallback(async (payload: {
    sessionId: string
    message: string
    projectId: string
    providerId: string
    modelId: string
  }) => {
    overlay.prepareExecutionRun({
      sessionId: payload.sessionId,
      message: payload.message,
    })

    const executionKey = `exec-${Date.now()}`

    try {
      await connectWebSocket(executionKey)
      startSocketExecution(payload)
    } catch (error) {
      console.error('Failed to start execution:', error)
    }
  }, [connectWebSocket, overlay, startSocketExecution])

  const handleCancel = useCallback(async () => {
    if (!overlay.currentExecutionIdRef.current) {
      return
    }

    startCancelling()

    try {
      await agentApi.cancel(overlay.currentExecutionIdRef.current)
    } catch (error) {
      console.error('Failed to cancel execution:', error)
      setStatus('running')
      setCanCancel(true)
      setPhase(phase || 'thinking')
    }
  }, [overlay.currentExecutionIdRef, phase, setCanCancel, setPhase, setStatus, startCancelling])

  const resetExecutionRuntime = useCallback(() => {
    closeWebSocket()
    overlay.resetExecutionOverlay()
    resetExecution()
  }, [closeWebSocket, overlay, resetExecution])

  useEffect(() => {
    if (!shouldResetOverlayForSessionChange(currentSessionId, overlay.activeSessionIdRef.current)) {
      return
    }

    closeWebSocket()
    overlay.resetExecutionOverlay()
    resetExecution()
  }, [closeWebSocket, currentSessionId, overlay, resetExecution])

  return {
    overlayItems: overlay.overlayItems,
    activeRoundItems: overlay.activeRoundItems,
    connectionStatus,
    startExecutionRun,
    handleCancel,
    resetExecutionRuntime,
  }
}
