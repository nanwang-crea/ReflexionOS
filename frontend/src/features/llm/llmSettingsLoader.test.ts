import { describe, expect, it, vi } from 'vitest'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'
import { createLLMSettingsLoader } from './llmSettingsLoader'

interface SettingsLoaderState {
  loaded: boolean
  providers: ProviderInstance[]
  defaultProviderId: string | null
  defaultModelId: string | null
  configured: boolean
}

function createProvider(id: string, modelId: string): ProviderInstance {
  return {
    id,
    name: id,
    provider_type: 'openai_compatible',
    enabled: true,
    default_model_id: modelId,
    models: [
      {
        id: modelId,
        display_name: modelId,
        model_name: modelId,
        enabled: true,
      },
    ],
  }
}

function applySettingsState(
  state: SettingsLoaderState,
  providers: ProviderInstance[],
  selection: DefaultLLMSelection
) {
  state.providers = providers
  state.defaultProviderId = selection.provider_id
  state.defaultModelId = selection.model_id
  state.configured = selection.configured
  state.loaded = true
}

describe('createLLMSettingsLoader', () => {
  it('deduplicates concurrent loads and stores the resolved settings', async () => {
    const state: SettingsLoaderState = {
      loaded: false,
      providers: [],
      defaultProviderId: null,
      defaultModelId: null,
      configured: false,
    }
    const providers = [createProvider('provider-a', 'model-a')]
    const selection: DefaultLLMSelection = {
      provider_id: 'provider-a',
      model_id: 'model-a',
      configured: true,
    }
    const getProviders = vi.fn(async () => providers)
    const getDefaultSelection = vi.fn(async () => selection)
    const loader = createLLMSettingsLoader({
      isDemoMode: () => false,
      getDemoProviders: () => [],
      getDemoSelection: () => ({
        provider_id: null,
        model_id: null,
        configured: false,
      }),
      getProviders,
      getDefaultSelection,
      getState: () => state,
      setLLMState: ({ providers: nextProviders, selection: nextSelection }) => {
        applySettingsState(state, nextProviders, nextSelection)
      },
    })

    const [first, second] = await Promise.all([loader(), loader()])

    expect(getProviders).toHaveBeenCalledTimes(1)
    expect(getDefaultSelection).toHaveBeenCalledTimes(1)
    expect(first).toEqual({ providers, selection })
    expect(second).toEqual({ providers, selection })
    expect(state.loaded).toBe(true)
  })

  it('returns the existing store snapshot when settings are already loaded', async () => {
    const state: SettingsLoaderState = {
      loaded: true,
      providers: [createProvider('provider-a', 'model-a')],
      defaultProviderId: 'provider-a',
      defaultModelId: 'model-a',
      configured: true,
    }
    const getProviders = vi.fn(async () => [])
    const getDefaultSelection = vi.fn(async () => ({
      provider_id: null,
      model_id: null,
      configured: false,
    }))
    const loader = createLLMSettingsLoader({
      isDemoMode: () => false,
      getDemoProviders: () => [],
      getDemoSelection: () => ({
        provider_id: null,
        model_id: null,
        configured: false,
      }),
      getProviders,
      getDefaultSelection,
      getState: () => state,
      setLLMState: () => undefined,
    })

    const loadedSettings = await loader()

    expect(getProviders).not.toHaveBeenCalled()
    expect(getDefaultSelection).not.toHaveBeenCalled()
    expect(loadedSettings.selection).toEqual({
      provider_id: 'provider-a',
      model_id: 'model-a',
      configured: true,
    })
  })
})
