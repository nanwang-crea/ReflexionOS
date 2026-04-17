import { create } from 'zustand'

export type ExecutionStatus = 'idle' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled'
export type ExecutionPhase = 'thinking' | 'executing' | 'summarizing' | null

interface ExecutionState {
  status: ExecutionStatus
  phase: ExecutionPhase
  executionId: string | null
  sessionId: string | null
  canCancel: boolean
  
  setStatus: (status: ExecutionStatus) => void
  setPhase: (phase: ExecutionPhase) => void
  setExecutionId: (id: string | null) => void
  setSessionId: (id: string | null) => void
  setCanCancel: (canCancel: boolean) => void
  
  startExecution: (id: string, sessionId: string | null) => void
  setThinkingPhase: () => void
  setExecutingPhase: () => void
  setSummarizingPhase: () => void
  startCancelling: () => void
  completeExecution: () => void
  failExecution: () => void
  cancelExecution: () => void
  resetExecution: () => void
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  status: 'idle',
  phase: null,
  executionId: null,
  sessionId: null,
  canCancel: false,
  
  setStatus: (status) => set({ status }),
  setPhase: (phase) => set({ phase }),
  setExecutionId: (id) => set({ executionId: id }),
  setSessionId: (id) => set({ sessionId: id }),
  setCanCancel: (canCancel) => set({ canCancel }),
  
  startExecution: (id, sessionId) => set({
    status: 'running',
    phase: 'thinking',
    executionId: id,
    sessionId,
    canCancel: true
  }),
  
  setThinkingPhase: () => set((state) => (
    state.status === 'running'
      ? { phase: 'thinking' }
      : {}
  )),

  setExecutingPhase: () => set((state) => (
    state.status === 'running'
      ? { phase: 'executing' }
      : {}
  )),

  setSummarizingPhase: () => set((state) => (
    state.status === 'running'
      ? { phase: 'summarizing' }
      : {}
  )),

  startCancelling: () => set((state) => (
    state.status === 'running'
      ? { status: 'cancelling', canCancel: false }
      : {}
  )),

  completeExecution: () => set({
    status: 'completed',
    phase: null,
    executionId: null,
    sessionId: null,
    canCancel: false
  }),

  failExecution: () => set({
    status: 'failed',
    phase: null,
    executionId: null,
    sessionId: null,
    canCancel: false
  }),

  cancelExecution: () => set({
    status: 'cancelled',
    phase: null,
    executionId: null,
    sessionId: null,
    canCancel: false
  }),
  
  resetExecution: () => set({
    status: 'idle',
    phase: null,
    executionId: null,
    sessionId: null,
    canCancel: false
  })
}))
