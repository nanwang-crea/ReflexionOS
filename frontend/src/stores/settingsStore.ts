import { create } from 'zustand'
import {
  demoDefaultLLMSelection,
  demoProviders,
  isDemoMode,
} from '@/demo/demoData'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

interface SettingsState {
  providers: ProviderInstance[]
  defaultProviderId: string | null
  defaultModelId: string | null
  configured: boolean
  loaded: boolean
  setProviders: (providers: ProviderInstance[]) => void
  setDefaultSelection: (selection: DefaultLLMSelection) => void
  setConfigured: (configured: boolean) => void
  setLoaded: (loaded: boolean) => void
  setLLMState: (payload: {
    providers: ProviderInstance[]
    selection: DefaultLLMSelection
  }) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  providers: isDemoMode() ? demoProviders : [],
  defaultProviderId: isDemoMode() ? demoDefaultLLMSelection.provider_id : null,
  defaultModelId: isDemoMode() ? demoDefaultLLMSelection.model_id : null,
  configured: isDemoMode() ? demoDefaultLLMSelection.configured : false,
  loaded: isDemoMode(),

  setProviders: (providers) => set({ providers }),

  setDefaultSelection: (selection) => set({
    defaultProviderId: selection.provider_id,
    defaultModelId: selection.model_id,
    configured: selection.configured,
  }),

  setConfigured: (configured) => set({ configured }),
  setLoaded: (loaded) => set({ loaded }),

  setLLMState: ({ providers, selection }) => set({
    providers,
    defaultProviderId: selection.provider_id,
    defaultModelId: selection.model_id,
    configured: selection.configured,
    loaded: true,
  }),
}))
