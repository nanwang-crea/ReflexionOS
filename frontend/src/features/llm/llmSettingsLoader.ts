import {
  demoDefaultLLMSelection,
  demoProviders,
  isDemoMode,
} from '@/demo/demoData'
import { llmApi } from '@/services/apiClient'
import { useSettingsStore } from '@/stores/settingsStore'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

export interface LoadedLLMSettings {
  providers: ProviderInstance[]
  selection: DefaultLLMSelection
}

interface LLMSettingsLoaderState {
  loaded: boolean
  providers: ProviderInstance[]
  defaultProviderId: string | null
  defaultModelId: string | null
  configured: boolean
}

interface CreateLLMSettingsLoaderOptions {
  isDemoMode: () => boolean
  getDemoProviders: () => ProviderInstance[]
  getDemoSelection: () => DefaultLLMSelection
  getProviders: () => Promise<ProviderInstance[]>
  getDefaultSelection: () => Promise<DefaultLLMSelection>
  getState: () => LLMSettingsLoaderState
  setLLMState: (settings: LoadedLLMSettings) => void
}

function createLoadedSnapshot(state: LLMSettingsLoaderState): LoadedLLMSettings {
  return {
    providers: state.providers,
    selection: {
      provider_id: state.defaultProviderId,
      model_id: state.defaultModelId,
      configured: state.configured,
    },
  }
}

export function createLLMSettingsLoader(options: CreateLLMSettingsLoaderOptions) {
  let inFlight: Promise<LoadedLLMSettings> | null = null

  return async function ensureLLMSettingsLoaded({ force = false }: { force?: boolean } = {}) {
    const state = options.getState()
    if (!force && state.loaded) {
      return createLoadedSnapshot(state)
    }

    if (inFlight) {
      return inFlight
    }

    inFlight = (async () => {
      const settings = options.isDemoMode()
        ? {
            providers: options.getDemoProviders(),
            selection: options.getDemoSelection(),
          }
        : {
            providers: await options.getProviders(),
            selection: await options.getDefaultSelection(),
          }

      options.setLLMState(settings)
      return settings
    })().finally(() => {
      inFlight = null
    })

    return inFlight
  }
}

const ensureLLMSettingsLoadedInternal = createLLMSettingsLoader({
  isDemoMode,
  getDemoProviders: () => demoProviders,
  getDemoSelection: () => demoDefaultLLMSelection,
  getProviders: async () => {
    const response = await llmApi.getProviders()
    return response.data
  },
  getDefaultSelection: async () => {
    const response = await llmApi.getDefaultSelection()
    return response.data
  },
  getState: () => useSettingsStore.getState(),
  setLLMState: (settings) => useSettingsStore.getState().setLLMState(settings),
})

export function ensureLLMSettingsLoaded(options?: { force?: boolean }) {
  return ensureLLMSettingsLoadedInternal(options)
}
