import { llmApi } from '@/services/apiClient'
import { useSettingsStore } from '@/stores/settingsStore'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'
import { cloneProvider, createEmptyProvider } from './providerDraft'

interface LoadedLLMSettings {
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
  getProviders: () => Promise<ProviderInstance[]>
  getDefaultSelection: () => Promise<DefaultLLMSelection>
  getState: () => LLMSettingsLoaderState
  setLLMState: (settings: LoadedLLMSettings) => void
}

interface SettingsPageLoaderOptions {
  ensureSettingsLoaded: (options?: { force?: boolean }) => Promise<LoadedLLMSettings>
  resetStoredSettings: () => void
}

interface SettingsPageLoadStateOptions {
  preferredProviderId?: string | null
  setLoading: (loading: boolean) => void
  setProviders: (providers: ProviderInstance[]) => void
  setDefaultSelection: (selection: DefaultLLMSelection) => void
  setSelectedProviderId: (providerId: string | null) => void
  setDraftProvider: (provider: ProviderInstance) => void
}

function createEmptySelection(): DefaultLLMSelection {
  return {
    provider_id: null,
    model_id: null,
    configured: false,
  }
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

export function createSettingsPageLoader(options: SettingsPageLoaderOptions) {
  return async function loadSettings({
    preferredProviderId,
    setLoading,
    setProviders,
    setDefaultSelection,
    setSelectedProviderId,
    setDraftProvider,
  }: SettingsPageLoadStateOptions) {
    setLoading(true)

    try {
      const loadedSettings = await options.ensureSettingsLoaded({
        force: preferredProviderId !== undefined,
      })
      const nextProviders = loadedSettings.providers
      const nextSelection = loadedSettings.selection

      setProviders(nextProviders)
      setDefaultSelection(nextSelection)

      const nextSelectedProvider = nextProviders.find((provider) => provider.id === preferredProviderId)
        || nextProviders[0]
        || null

      if (nextSelectedProvider) {
        setSelectedProviderId(nextSelectedProvider.id)
        setDraftProvider(cloneProvider(nextSelectedProvider))
      } else {
        setSelectedProviderId(null)
        setDraftProvider(createEmptyProvider())
      }
    } catch (error) {
      console.error('Failed to load LLM settings:', error)
      options.resetStoredSettings()
      setProviders([])
      setDefaultSelection(createEmptySelection())
      setSelectedProviderId(null)
      setDraftProvider(createEmptyProvider())
    } finally {
      setLoading(false)
    }
  }
}

export function resetLLMSettingsStore() {
  useSettingsStore.setState({
    providers: [],
    defaultProviderId: null,
    defaultModelId: null,
    configured: false,
    loaded: false,
  })
}
