import { create } from 'zustand'
import { Message } from '@/types/agent'

type ExecutionStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

interface AgentState {
  messages: Message[]
  executionStatus: ExecutionStatus
  currentStep: number
  totalSteps: number
  task: string
  
  addMessage: (message: Message) => void
  setExecutionStatus: (status: ExecutionStatus) => void
  updateProgress: (current: number, total: number) => void
  setTask: (task: string) => void
  reset: () => void
}

export const useAgentStore = create<AgentState>((set) => ({
  messages: [],
  executionStatus: 'idle',
  currentStep: 0,
  totalSteps: 0,
  task: '',
  
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message]
  })),
  
  setExecutionStatus: (status) => set({ executionStatus: status }),
  
  updateProgress: (current, total) => set({
    currentStep: current,
    totalSteps: total
  }),
  
  setTask: (task) => set({ task }),
  
  reset: () => set({
    messages: [],
    executionStatus: 'idle',
    currentStep: 0,
    totalSteps: 0,
    task: ''
  }),
}))
