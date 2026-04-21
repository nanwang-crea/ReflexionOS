import { useCallback, useEffect } from 'react'
import { ensureSessionHistoryLoaded, refreshSessionHistory } from '@/features/sessions/sessionLoader'
import { agentApi } from '@/services/apiClient'
import { shouldResetOverlayForSessionChange } from './executionOverlayState'
import { useExecutionStore } from '@/stores/executionStore'
import { useExecutionDraftRound } from './useExecutionDraftRound'
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

  const draftRound = useExecutionDraftRound()
  const overlay = useExecutionOverlay(draftRound)
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
    draftRound: {
      clearDraftRound: draftRound.clearDraftRound,
      refreshSessionHistory,
    },
  })

  const loadSessionHistory = useCallback(async (sessionId: string) => {
    await ensureSessionHistoryLoaded(sessionId)
  }, [])

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
    draftRound.clearDraftRound()
    resetExecution()
  }, [closeWebSocket, draftRound, overlay, resetExecution])

  useEffect(() => {
    if (!shouldResetOverlayForSessionChange(currentSessionId, draftRound.sessionIdRef.current)) {
      return
    }

    closeWebSocket()
    overlay.resetExecutionOverlay()
    draftRound.clearDraftRound()
    resetExecution()
  }, [closeWebSocket, currentSessionId, draftRound, overlay, resetExecution])

  return {
    overlayItems: overlay.overlayItems,
    activeRoundItems: draftRound.items,
    connectionStatus,
    loadSessionHistory,
    startExecutionRun,
    handleCancel,
    resetExecutionRuntime,
  }
}
