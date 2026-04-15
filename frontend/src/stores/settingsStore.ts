import { create } from 'zustand'
import { LLMConfig } from '@/types/llm'

interface SettingsState {
  llmConfig: LLMConfig | null
  configured: boolean
  setLLMConfig: (config: LLMConfig) => void
  setConfigured: (configured: boolean) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  llmConfig: null,
  configured: false,
  
  setLLMConfig: (config) => set({ 
    llmConfig: config,
    configured: true 
  }),
  
  setConfigured: (configured) => set({ configured }),
}))
