import { create } from 'zustand'

export type ExecutionStatus = 'idle' | 'running' | 'paused' | 'stopped'

interface ExecutionState {
  status: ExecutionStatus
  executionId: string | null
  canPause: boolean
  canStop: boolean
  
  setStatus: (status: ExecutionStatus) => void
  setExecutionId: (id: string | null) => void
  setCanPause: (canPause: boolean) => void
  setCanStop: (canStop: boolean) => void
  
  startExecution: (id: string) => void
  pauseExecution: () => void
  resumeExecution: () => void
  stopExecution: () => void
  resetExecution: () => void
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  status: 'idle',
  executionId: null,
  canPause: false,
  canStop: false,
  
  setStatus: (status) => set({ status }),
  setExecutionId: (id) => set({ executionId: id }),
  setCanPause: (canPause) => set({ canPause }),
  setCanStop: (canStop) => set({ canStop }),
  
  startExecution: (id) => set({
    status: 'running',
    executionId: id,
    canPause: true,
    canStop: true
  }),
  
  pauseExecution: () => {
    const { status } = get()
    if (status === 'running') {
      set({ status: 'paused', canPause: false })
    }
  },
  
  resumeExecution: () => {
    const { status } = get()
    if (status === 'paused') {
      set({ status: 'running', canPause: true })
    }
  },
  
  stopExecution: () => set({
    status: 'stopped',
    canPause: false,
    canStop: false
  }),
  
  resetExecution: () => set({
    status: 'idle',
    executionId: null,
    canPause: false,
    canStop: false
  })
}))
