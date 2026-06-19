import { create } from 'zustand'
import { createEmptySelection } from '@/utils/llmHelpers'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

interface SettingsState {
  providers: ProviderInstance[]
  defaultSelection: DefaultLLMSelection
  defaultProviderId: string | null
  defaultModelId: string | null
  configured: boolean
  loaded: boolean
  showProcessExpanded: boolean
  autoCollapseProcess: boolean
  uiSettingsLoaded: boolean
  setLLMState: (payload: {
    providers: ProviderInstance[]
    selection: DefaultLLMSelection
  }) => void
  setUISetting: (payload: {
    showProcessExpanded: boolean
    autoCollapseProcess: boolean
  }) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  providers: [],
  defaultSelection: createEmptySelection(),
  defaultProviderId: null,
  defaultModelId: null,
  configured: false,
  loaded: false,
  showProcessExpanded: true,
  autoCollapseProcess: true,
  uiSettingsLoaded: false,

  setLLMState: ({ providers, selection }) => set({
    providers,
    defaultSelection: selection,
    defaultProviderId: selection.provider_id,
    defaultModelId: selection.model_id,
    configured: selection.configured,
    loaded: true,
  }),

  setUISetting: ({ showProcessExpanded, autoCollapseProcess }) => set({
    showProcessExpanded,
    autoCollapseProcess,
    uiSettingsLoaded: true,
  }),
}))
