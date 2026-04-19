import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

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

const getProvidersMock = vi.fn()
const getDefaultSelectionMock = vi.fn()

vi.mock('@/demo/demoData', () => ({
  isDemoMode: () => false,
  demoProviders: [],
  demoDefaultLLMSelection: {
    provider_id: null,
    model_id: null,
    configured: false,
  },
}))

vi.mock('@/services/apiClient', () => ({
  llmApi: {
    getProviders: getProvidersMock,
    getDefaultSelection: getDefaultSelectionMock,
  },
}))

beforeEach(() => {
  vi.resetModules()
  getProvidersMock.mockReset()
  getDefaultSelectionMock.mockReset()
})

describe('ensureLLMSettingsLoaded', () => {
  it('deduplicates concurrent loads and stores the resolved settings', async () => {
    const providers = [createProvider('provider-a', 'model-a')]
    const selection: DefaultLLMSelection = {
      provider_id: 'provider-a',
      model_id: 'model-a',
      configured: true,
    }
    getProvidersMock.mockResolvedValue({ data: providers })
    getDefaultSelectionMock.mockResolvedValue({ data: selection })

    const { useSettingsStore } = await import('@/stores/settingsStore')
    useSettingsStore.setState({
      providers: [],
      defaultProviderId: null,
      defaultModelId: null,
      configured: false,
      loaded: false,
    })

    const { ensureLLMSettingsLoaded } = await import('./llmSettingsLoader')
    const [first, second] = await Promise.all([ensureLLMSettingsLoaded(), ensureLLMSettingsLoaded()])

    expect(getProvidersMock).toHaveBeenCalledTimes(1)
    expect(getDefaultSelectionMock).toHaveBeenCalledTimes(1)
    expect(first).toEqual({ providers, selection })
    expect(second).toEqual({ providers, selection })
    expect(useSettingsStore.getState().loaded).toBe(true)
  })

  it('returns the existing store snapshot when settings are already loaded', async () => {
    const { useSettingsStore } = await import('@/stores/settingsStore')
    useSettingsStore.setState({
      providers: [createProvider('provider-a', 'model-a')],
      defaultProviderId: 'provider-a',
      defaultModelId: 'model-a',
      configured: true,
      loaded: true,
    })

    const { ensureLLMSettingsLoaded } = await import('./llmSettingsLoader')
    const loadedSettings = await ensureLLMSettingsLoaded()

    expect(getProvidersMock).not.toHaveBeenCalled()
    expect(getDefaultSelectionMock).not.toHaveBeenCalled()
    expect(loadedSettings.selection).toEqual({
      provider_id: 'provider-a',
      model_id: 'model-a',
      configured: true,
    })
  })
})
