/**
 * 文件功能：llmSettings.loader / provider.actions / providerDraft 的单元测试
 * 文件描述：覆盖 LLM 设置加载去重与缓存复用、store 重置、供应商草稿的规范化与
 *          校验、以及保存/删除供应商和设置页面 action 组装等场景。
 * 核心逻辑：通过 vi.mock 对 llmApi 打桩，每个测试用例内部按需 mockResolvedValue，
 *          并用 vi.resetModules() + 各 mock.mockReset() 保证测试间状态互不影响。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

/**
 * 函数名：createProvider（测试辅助函数）
 * 入参：
 *   - id (string): 供应商 id（同时用作 name）
 *   - modelId (string): 供应商下唯一模型的 id（同时用作 display_name/model_name）
 * 功能：快速构造一个结构完整的最小化 ProviderInstance 测试夹具
 * 运行逻辑：固定 provider_type 为 'openai_compatible'，仅包含一个已启用模型，
 *          并将该模型设为 default_model_id
 * 出参：ProviderInstance - 构造好的供应商测试对象
 */
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

vi.mock('../api/llm.api', () => ({
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
  // 场景：并发调用两次 ensureLLMSettingsLoaded，应只发起一次真实请求（请求去重），
  // 且两次调用都拿到同样的结果，最终 store 标记为已加载
  // 该用例在整套前端测试并发运行时会叠加动态 import / resetModules 成本，
  // 在 Windows CI 或高负载开发机上偶发超过 Vitest 默认 5s，显式放宽到 20s 避免误报。
  it('deduplicates concurrent loads and stores the resolved settings', async () => {
    const providers = [createProvider('provider-a', 'model-a')]
    const selection: DefaultLLMSelection = {
      provider_id: 'provider-a',
      model_id: 'model-a',
      configured: true,
    }
    getProvidersMock.mockResolvedValue({ data: providers })
    getDefaultSelectionMock.mockResolvedValue({ data: selection })

    const { useSettingsStore } = await import('@/features/settings/stores/settings.store')
    useSettingsStore.setState({
      providers: [],
      defaultSelection: { provider_id: null, model_id: null, configured: false },
      defaultProviderId: null,
      defaultModelId: null,
      configured: false,
      loaded: false,
    })

    const { ensureLLMSettingsLoaded } = await import('../llmSettings.loader')
    const [first, second] = await Promise.all([ensureLLMSettingsLoaded(), ensureLLMSettingsLoaded()])

    expect(getProvidersMock).toHaveBeenCalledTimes(1)
    expect(getDefaultSelectionMock).toHaveBeenCalledTimes(1)
    expect(first).toEqual({ providers, selection })
    expect(second).toEqual({ providers, selection })
    expect(useSettingsStore.getState().loaded).toBe(true)
  }, 20000)

  // 场景：store 中已标记 loaded=true 时，不应再发起任何网络请求，直接复用缓存快照
  it('returns the existing store snapshot when settings are already loaded', async () => {
    const { useSettingsStore } = await import('@/features/settings/stores/settings.store')
    useSettingsStore.setState({
      providers: [createProvider('provider-a', 'model-a')],
      defaultSelection: { provider_id: 'provider-a', model_id: 'model-a', configured: true },
      defaultProviderId: 'provider-a',
      defaultModelId: 'model-a',
      configured: true,
      loaded: true,
    })

    const { ensureLLMSettingsLoaded } = await import('../llmSettings.loader')
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

describe('resetLLMSettingsStore', () => {
  // 场景：调用 resetLLMSettingsStore 后，store 应恢复为空列表 + 未加载的初始状态
  it('resets stored settings to an unloaded state', async () => {
    const { useSettingsStore } = await import('@/features/settings/stores/settings.store')
    const { resetLLMSettingsStore } = await import('../llmSettings.loader')

    useSettingsStore.setState({
      providers: [createProvider('provider-a', 'model-a')],
      defaultSelection: { provider_id: 'provider-a', model_id: 'model-a', configured: true },
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
  // 场景：normalizeProviderDraft 应 trim 掉 name/api_key/base_url 及各模型字段首尾空格
  it('normalizes provider draft by trimming fields', async () => {
    const { normalizeProviderDraft } = await import('../providerDraft')

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
    expect(normalized.default_model_id).toBe('')
  })

  // 场景：模型的 model_name 为空时，validateProviderDraft 应返回对应的中文错误提示
  it('rejects provider drafts with empty model fields', async () => {
    const { validateProviderDraft } = await import('../providerDraft')

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
  // 场景：已有 selectedSavedProvider 时保存草稿应走 updateProvider（而非 createProvider），
  // 保存成功后应以草稿 id 重新加载设置，并触发保存成功提示
  it('saves a normalized provider and reloads settings with the draft id', async () => {
    const updateProvider = vi.fn().mockResolvedValue(undefined)
    const createProvider = vi.fn().mockResolvedValue(undefined)
    const loadSettings = vi.fn().mockResolvedValue(undefined)
    const onSavedMessage = vi.fn()
    const onError = vi.fn()
    const setSaving = vi.fn()

    const { createProviderActions } = await import('../provider.actions')
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
    }))
    expect(createProvider).not.toHaveBeenCalled()
    expect(loadSettings).toHaveBeenCalledWith('provider-a')
    expect(onSavedMessage).toHaveBeenCalledWith('供应商已保存')
    expect(onError).not.toHaveBeenCalled()
    expect(setSaving).toHaveBeenNthCalledWith(1, true)
    expect(setSaving).toHaveBeenLastCalledWith(false)
  })

  // 场景：删除供应商前需经 confirmDelete 确认，删除成功后应以 null 强制刷新设置（不复用缓存）
  it('deletes a provider and forces settings reload instead of reusing cached settings', async () => {
    const deleteProvider = vi.fn().mockResolvedValue(undefined)
    const loadSettings = vi.fn().mockResolvedValue(undefined)
    const onSavedMessage = vi.fn()
    const onError = vi.fn()
    const confirmDelete = vi.fn().mockResolvedValue(true)

    const { createProviderActions } = await import('../provider.actions')
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

  // 场景：createSettingsPageActions 应自动注入真实 llmApi 和 setLLMState，
  // 调用方无需关心这两项依赖的具体实现
  it('composes settings page actions without passing api or store orchestration from the page', async () => {
    const loadSettings = vi.fn().mockResolvedValue(undefined)
    const onSavedMessage = vi.fn()
    const onError = vi.fn()
    const setSaving = vi.fn()
    const { useSettingsStore } = await import('@/features/settings/stores/settings.store')
    const setLLMStateSpy = vi.spyOn(useSettingsStore.getState(), 'setLLMState')

    updateProviderMock.mockResolvedValue(undefined)

    const { createSettingsPageActions } = await import('../provider.actions')
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
