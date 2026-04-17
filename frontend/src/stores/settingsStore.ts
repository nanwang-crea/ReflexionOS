import { create } from 'zustand'
import { demoLLMConfig, isDemoMode } from '@/demo/demoData'
import { LLMConfig } from '@/types/llm'

interface SettingsState {
  llmConfig: LLMConfig | null
  configured: boolean
  setLLMConfig: (config: LLMConfig) => void
  setConfigured: (configured: boolean) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  llmConfig: isDemoMode() ? demoLLMConfig : null,
  configured: isDemoMode(),
  
  setLLMConfig: (config) => set({ 
    llmConfig: config,
    configured: true 
  }),
  
  setConfigured: (configured) => set({ configured }),
}))
