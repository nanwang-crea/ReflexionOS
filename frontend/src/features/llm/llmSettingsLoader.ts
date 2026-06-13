import { llmApi } from './llmApi'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

interface LoadedLLMSettings {
  providers: ProviderInstance[]
  selection: DefaultLLMSelection
}

interface LLMSettingsLoaderState {
  loaded: boolean
  providers: ProviderInstance[]
  defaultSelection: DefaultLLMSelection
}

interface CreateLLMSettingsLoaderOptions {
  getProviders: () => Promise<ProviderInstance[]>
  getDefaultSelection: () => Promise<DefaultLLMSelection>
  getState: () => LLMSettingsLoaderState
  setLLMState: (settings: LoadedLLMSettings) => void
}

function createLoadedSnapshot(state: LLMSettingsLoaderState): LoadedLLMSettings {
  return {
    providers: state.providers,
    selection: state.defaultSelection,
  }
}

function createLLMSettingsLoader(options: CreateLLMSettingsLoaderOptions) {
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
      const settings = {
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

export function resetLLMSettingsStore() {
  useSettingsStore.setState({
    providers: [],
    defaultSelection: { provider_id: null, model_id: null, configured: false },
    defaultProviderId: null,
    defaultModelId: null,
    configured: false,
    loaded: false,
  })
}
