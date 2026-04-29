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
const createProviderMock = vi.fn()
const updateProviderMock = vi.fn()
const deleteProviderMock = vi.fn()
const testProviderMock = vi.fn()
const setDefaultSelectionMock = vi.fn()

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
    createProvider: createProviderMock,
    updateProvider: updateProviderMock,
    deleteProvider: deleteProviderMock,
    testProvider: testProviderMock,
    setDefaultSelection: setDefaultSelectionMock,
  },
}))

beforeEach(() => {
  vi.resetModules()
  getProvidersMock.mockReset()
  getDefaultSelectionMock.mockReset()
  createProviderMock.mockReset()
  updateProviderMock.mockReset()
  deleteProviderMock.mockReset()
  testProviderMock.mockReset()
  setDefaultSelectionMock.mockReset()
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

describe('settings page loader', () => {
  it('loads settings into page state and selects the preferred provider when present', async () => {
    const providers = [createProvider('provider-a', 'model-a'), createProvider('provider-b', 'model-b')]
    const selection: DefaultLLMSelection = {
      provider_id: 'provider-a',
      model_id: 'model-a',
      configured: true,
    }
    const setLoading = vi.fn()
    const setProviders = vi.fn()
    const setDefaultSelection = vi.fn()
    const setSelectedProviderId = vi.fn()
    const setDraftProvider = vi.fn()

    const { createSettingsPageLoader } = await import('./llmSettingsLoader')
    const loadSettings = createSettingsPageLoader({
      ensureSettingsLoaded: vi.fn().mockResolvedValue({ providers, selection }),
      resetStoredSettings: vi.fn(),
    })

    await loadSettings({
      preferredProviderId: 'provider-b',
      setLoading,
      setProviders,
      setDefaultSelection,
      setSelectedProviderId,
      setDraftProvider,
    })

    expect(setLoading).toHaveBeenNthCalledWith(1, true)
    expect(setProviders).toHaveBeenCalledWith(providers)
    expect(setDefaultSelection).toHaveBeenCalledWith(selection)
    expect(setSelectedProviderId).toHaveBeenCalledWith('provider-b')
    expect(setDraftProvider).toHaveBeenCalledWith(expect.objectContaining({ id: 'provider-b' }))
    expect(setLoading).toHaveBeenLastCalledWith(false)
  })

  it('resets page and store state when loading settings fails', async () => {
    const setLoading = vi.fn()
    const setProviders = vi.fn()
    const setDefaultSelection = vi.fn()
    const setSelectedProviderId = vi.fn()
    const setDraftProvider = vi.fn()
    const resetStoredSettings = vi.fn()

    const { createSettingsPageLoader } = await import('./llmSettingsLoader')
    const loadSettings = createSettingsPageLoader({
      ensureSettingsLoaded: vi.fn().mockRejectedValue(new Error('boom')),
      resetStoredSettings,
    })

    await loadSettings({
      setLoading,
      setProviders,
      setDefaultSelection,
      setSelectedProviderId,
      setDraftProvider,
    })

    expect(resetStoredSettings).toHaveBeenCalledTimes(1)
    expect(setProviders).toHaveBeenCalledWith([])
    expect(setDefaultSelection).toHaveBeenCalledWith({
      provider_id: null,
      model_id: null,
      configured: false,
    })
    expect(setSelectedProviderId).toHaveBeenCalledWith(null)
    expect(setDraftProvider).toHaveBeenCalledWith(expect.objectContaining({ name: '' }))
    expect(setLoading).toHaveBeenLastCalledWith(false)
  })

  it('resets stored settings to an unloaded state after load failure', async () => {
    const { useSettingsStore } = await import('@/stores/settingsStore')
    const { resetLLMSettingsStore } = await import('./llmSettingsLoader')

    useSettingsStore.setState({
      providers: [createProvider('provider-a', 'model-a')],
      defaultProviderId: 'provider-a',
      defaultModelId: 'model-a',
      configured: true,
      loaded: true,
    })

    resetLLMSettingsStore()

    expect(useSettingsStore.getState()).toMatchObject({
      providers: [],
      defaultProviderId: null,
      defaultModelId: null,
      configured: false,
      loaded: false,
    })
  })
})

describe('providerDraft helpers', () => {
  it('normalizes provider draft with fallback default model id', async () => {
    const { normalizeProviderDraft } = await import('./providerDraft')

    const normalized = normalizeProviderDraft({
      id: 'provider-a',
      name: ' OpenAI ',
      provider_type: 'openai_compatible',
      api_key: ' secret ',
      base_url: ' https://api.example.com ',
      enabled: true,
      default_model_id: '',
      models: [
        {
          id: 'model-1',
          display_name: ' GPT-4.1 ',
          model_name: ' gpt-4.1 ',
          enabled: true,
        },
      ],
    })

    expect(normalized.name).toBe('OpenAI')
    expect(normalized.api_key).toBe('secret')
    expect(normalized.base_url).toBe('https://api.example.com')
    expect(normalized.models[0]).toMatchObject({
      display_name: 'GPT-4.1',
      model_name: 'gpt-4.1',
    })
    expect(normalized.default_model_id).toBe('model-1')
  })

  it('rejects provider drafts with empty model fields', async () => {
    const { validateProviderDraft } = await import('./providerDraft')

    expect(validateProviderDraft({
      id: 'provider-a',
      name: 'OpenAI',
      provider_type: 'openai_compatible',
      enabled: true,
      default_model_id: 'model-1',
      models: [
        {
          id: 'model-1',
          display_name: 'GPT-4.1',
          model_name: '',
          enabled: true,
        },
      ],
    })).toBe('模型显示名称和模型名称不能为空')
  })
})

describe('providerActions', () => {
  it('saves a normalized provider and reloads settings with the draft id', async () => {
    const updateProvider = vi.fn().mockResolvedValue(undefined)
    const createProvider = vi.fn().mockResolvedValue(undefined)
    const loadSettings = vi.fn().mockResolvedValue(undefined)
    const onSavedMessage = vi.fn()
    const onError = vi.fn()
    const setSaving = vi.fn()

    const { createProviderActions } = await import('./providerActions')
    const actions = createProviderActions({
      api: {
        createProvider,
        updateProvider,
        deleteProvider: vi.fn(),
        testProvider: vi.fn(),
        setDefaultSelection: vi.fn(),
      },
      loadSettings,
      setLLMState: vi.fn(),
      setSaving,
      setSavingDefault: vi.fn(),
      setTesting: vi.fn(),
      onSavedMessage,
      onTestResult: vi.fn(),
      onError,
    })

    await actions.saveProvider({
      selectedSavedProvider: {
        id: 'provider-a',
        name: 'OpenAI',
        provider_type: 'openai_compatible',
        enabled: true,
        default_model_id: 'persisted-model',
        models: [
          {
            id: 'persisted-model',
            display_name: 'Persisted',
            model_name: 'persisted',
            enabled: true,
          },
        ],
      },
      draftProvider: {
        id: 'provider-a',
        name: ' OpenAI ',
        provider_type: 'openai_compatible',
        enabled: true,
        default_model_id: '',
        models: [
          {
            id: 'model-1',
            display_name: ' GPT-4.1 ',
            model_name: ' gpt-4.1 ',
            enabled: true,
          },
        ],
      },
    })

    expect(updateProvider).toHaveBeenCalledWith('provider-a', expect.objectContaining({
      name: 'OpenAI',
      default_model_id: 'model-1',
    }))
    expect(createProvider).not.toHaveBeenCalled()
    expect(loadSettings).toHaveBeenCalledWith('provider-a')
    expect(onSavedMessage).toHaveBeenCalledWith('供应商已保存')
    expect(onError).not.toHaveBeenCalled()
    expect(setSaving).toHaveBeenNthCalledWith(1, true)
    expect(setSaving).toHaveBeenLastCalledWith(false)
  })

  it('deletes a provider and forces settings reload instead of reusing cached settings', async () => {
    const deleteProvider = vi.fn().mockResolvedValue(undefined)
    const loadSettings = vi.fn().mockResolvedValue(undefined)
    const onSavedMessage = vi.fn()
    const onError = vi.fn()
    const confirmDelete = vi.fn().mockReturnValue(true)

    const { createProviderActions } = await import('./providerActions')
    const actions = createProviderActions({
      api: {
        createProvider: vi.fn(),
        updateProvider: vi.fn(),
        deleteProvider,
        testProvider: vi.fn(),
        setDefaultSelection: vi.fn(),
      },
      loadSettings,
      setLLMState: vi.fn(),
      setSaving: vi.fn(),
      setSavingDefault: vi.fn(),
      setTesting: vi.fn(),
      onSavedMessage,
      onTestResult: vi.fn(),
      onError,
    })

    await actions.deleteProvider({
      selectedSavedProvider: createProvider('provider-a', 'model-a'),
      resetDraft: vi.fn(),
      confirmDelete,
    })

    expect(confirmDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 'provider-a' }))
    expect(deleteProvider).toHaveBeenCalledWith('provider-a')
    expect(loadSettings).toHaveBeenCalledWith(null)
    expect(onSavedMessage).toHaveBeenCalledWith('供应商已删除')
    expect(onError).not.toHaveBeenCalled()
  })

  it('composes settings page actions without passing api or store orchestration from the page', async () => {
    const loadSettings = vi.fn().mockResolvedValue(undefined)
    const onSavedMessage = vi.fn()
    const onError = vi.fn()
    const setSaving = vi.fn()
    const { useSettingsStore } = await import('@/stores/settingsStore')
    const setLLMStateSpy = vi.spyOn(useSettingsStore.getState(), 'setLLMState')

    updateProviderMock.mockResolvedValue(undefined)

    const { createSettingsPageActions } = await import('./providerActions')
    const actions = createSettingsPageActions({
      loadSettings,
      setSaving,
      setSavingDefault: vi.fn(),
      setTesting: vi.fn(),
      onSavedMessage,
      onTestResult: vi.fn(),
      onError,
    })

    await actions.saveProvider({
      selectedSavedProvider: {
        id: 'provider-a',
        name: 'OpenAI',
        provider_type: 'openai_compatible',
        enabled: true,
        default_model_id: 'model-1',
        models: [{ id: 'model-1', display_name: 'Model 1', model_name: 'model-1', enabled: true }],
      },
      draftProvider: {
        id: 'provider-a',
        name: ' OpenAI ',
        provider_type: 'openai_compatible',
        enabled: true,
        default_model_id: 'model-1',
        models: [{ id: 'model-1', display_name: 'Model 1', model_name: 'model-1', enabled: true }],
      },
    })

    expect(updateProviderMock).toHaveBeenCalledTimes(1)
    expect(loadSettings).toHaveBeenCalledWith('provider-a')
    expect(setLLMStateSpy).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })
})
