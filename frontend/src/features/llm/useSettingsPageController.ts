/**
 * 文件功能：LLM 设置页面的控制器 hook
 * 文件描述：将设置页面（供应商列表、编辑表单、默认模型选择）所需的全部状态与交互
 *          逻辑集中在一个 hook 中，页面组件只负责渲染，不关心具体业务流程。
 * 核心逻辑：
 *   1. 首次挂载时加载设置（供应商列表 + 默认选择），并据此初始化表单草稿；
 *   2. 表单操作（选择/新建供应商、修改字段、增删模型）都是纯粹的本地状态更新；
 *   3. 保存/删除/测试连接/保存默认选择等"有副作用"的操作委托给 provider.actions.ts
 *      中创建的 action 方法执行，controller 只负责传入依赖和处理返回结果。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { nativeDialogService, type DialogService } from '@/services/dialogService'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import { useToastStore } from '@/shared/stores/toast.store'
import type { DefaultLLMSelection, ProviderInstance, ProviderModel } from '@/types/llm'
import { createEmptySelection, getEnabledModels } from '@/utils/llmHelpers'
import {
  applyProviderToDefaultSelection,
  cloneProvider,
  createEmptyModel,
  createEmptyProvider,
} from './providerDraft'
import {
  ensureLLMSettingsLoaded,
  resetLLMSettingsStore,
} from './llmSettings.loader'
import { createSettingsPageActions } from './provider.actions'

type TestResult = { type: 'success' | 'error'; message: string } | null

/**
 * 函数名：useSettingsPageController
 * 入参：
 *   - options ({ dialogService?, createActions? } | undefined): 可选依赖注入，
 *     dialogService 用于弹窗确认/错误提示，createActions 用于替换 action 工厂
 *     （主要用于单测中注入 mock 实现）
 * 功能：LLM 设置页面的完整状态与交互逻辑封装
 * 运行逻辑：
 *   1. 维护供应商列表（来自 store）、当前选中供应商、表单草稿、默认选择、
 *      各类 loading/提示状态；
 *   2. refreshSettings 负责调用 ensureLLMSettingsLoaded 拉取数据并同步到本地状态，
 *      失败时提示错误并重置为空草稿；
 *   3. 首次挂载时通过 useEffect 触发一次 refreshSettings（用 storeSelectionSeqRef
 *      记录是否已经刷新过，避免重复请求）；
 *   4. 各 handleXxx 回调分别处理选择供应商、新建供应商、字段修改、模型增删、
 *      保存/删除供应商、测试连接、切换/保存默认选择等交互；
 *   5. providerActions 通过 useMemo 创建，实际业务逻辑委托给 provider.actions.ts。
 * 出参：{ providers, selectedProviderId, draftProvider, defaultSelection, loading,
 *      saving, savingDefault, testing, savedMessage, testResult, selectedSavedProvider,
 *      defaultProviderModels, handleSelectProvider, handleCreateProvider,
 *      handleDraftFieldChange, handleModelFieldChange, handleAddModel, handleRemoveModel,
 *      handleSaveProvider, handleDeleteProvider, handleTestConnection,
 *      handleDefaultProviderChange, handleDefaultModelChange, handleSaveDefaultSelection }
 *      - 页面所需的全部状态与交互方法
 */
export function useSettingsPageController(options?: {
  dialogService?: DialogService
  createActions?: typeof createSettingsPageActions
}) {
  const storeProviders = useSettingsStore((s) => s.providers)
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null)
  const [draftProvider, setDraftProvider] = useState<ProviderInstance>(createEmptyProvider())
  const [defaultSelection, setDefaultSelection] = useState<DefaultLLMSelection>(createEmptySelection())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingDefault, setSavingDefault] = useState(false)
  const [testing, setTesting] = useState(false)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<TestResult>(null)

  const storeSelectionSeqRef = useRef(0)

  const providers = storeProviders

  const selectedSavedProvider = useMemo(
    () => providers.find((provider) => provider.id === selectedProviderId) || null,
    [providers, selectedProviderId]
  )
  const defaultProvider = useMemo(
    () => providers.find((provider) => provider.id === defaultSelection.provider_id) || null,
    [defaultSelection.provider_id, providers]
  )
  const defaultProviderModels = useMemo(
    () => getEnabledModels(defaultProvider),
    [defaultProvider]
  )

  // 重置表单草稿：清空选中供应商，恢复为空白供应商草稿，并清除保存/测试提示
  const resetDraft = useCallback(() => {
    setSelectedProviderId(null)
    setDraftProvider(createEmptyProvider())
    setSavedMessage(null)
    setTestResult(null)
  }, [])

  /**
   * 函数名：refreshSettings（useCallback 包裹）
   * 入参：
   *   - preferredProviderId (string | null | undefined): 刷新后优先选中的供应商 id；
   *     传入非 undefined 值会强制重新请求（忽略缓存）
   * 功能：拉取最新的 LLM 设置（供应商列表 + 默认选择）并同步到本地表单状态
   * 运行逻辑：调用 ensureLLMSettingsLoaded 获取数据；计算应选中的供应商
   *          （优先 preferredProviderId 命中的供应商，否则取列表第一个，否则为空）；
   *          据此更新 defaultSelection/selectedProviderId/draftProvider；
   *          请求失败则提示错误 toast，并将本地状态重置为空
   * 出参：Promise<void>
   */
  const refreshSettings = useCallback(async (preferredProviderId?: string | null) => {
    setLoading(true)

    try {
      const loadedSettings = await ensureLLMSettingsLoaded({
        force: preferredProviderId !== undefined,
      })

      const nextProviders = loadedSettings.providers
      const nextSelection = loadedSettings.selection
      const nextSelectedProvider = nextProviders.find((provider) => provider.id === preferredProviderId)
        || nextProviders[0]
        || null

      setDefaultSelection(nextSelection)
      storeSelectionSeqRef.current += 1

      if (nextSelectedProvider) {
        setSelectedProviderId(nextSelectedProvider.id)
        setDraftProvider(cloneProvider(nextSelectedProvider))
      } else {
        setSelectedProviderId(null)
        setDraftProvider(createEmptyProvider())
      }
    } catch (error) {
      console.error('Failed to load LLM settings:', error)
      useToastStore.getState().addToast('error', '加载 LLM 设置失败，请检查配置')
      resetLLMSettingsStore()
      setDefaultSelection(createEmptySelection())
      setSelectedProviderId(null)
      setDraftProvider(createEmptyProvider())
    } finally {
      setLoading(false)
    }
  }, [])

  // 首次挂载时刷新一次设置；storeSelectionSeqRef 用于避免重复触发（不是依赖数组去重）
  useEffect(() => {
    const currentSeq = storeSelectionSeqRef.current
    if (currentSeq > 0) {
      return
    }
    refreshSettings().catch((error) => {
      console.error('Failed to refresh settings:', error)
      useToastStore.getState().addToast('error', '刷新设置失败')
    })
  }, [refreshSettings])

  const dialogService = options?.dialogService || nativeDialogService

  // 组装供应商相关业务动作（保存/删除/测试连接/保存默认选择），委托给 provider.actions.ts
  const providerActions = useMemo(() => (options?.createActions || createSettingsPageActions)({
    loadSettings: refreshSettings,
    setSaving,
    setSavingDefault,
    setTesting,
    onSavedMessage: setSavedMessage,
    onTestResult: setTestResult,
    onError: dialogService.notifyError,
  }), [dialogService.notifyError, options?.createActions, refreshSettings])

  // 选中某个已保存的供应商：将其克隆为草稿，清除之前的保存/测试提示
  const handleSelectProvider = useCallback((providerId: string) => {
    const provider = providers.find((item) => item.id === providerId)
    if (!provider) {
      return
    }

    setSelectedProviderId(providerId)
    setDraftProvider(cloneProvider(provider))
    setSavedMessage(null)
    setTestResult(null)
  }, [providers])

  // 新建供应商：重置为空白草稿
  const handleCreateProvider = useCallback(() => {
    resetDraft()
  }, [resetDraft])

  // 修改草稿的顶层字段（如 name/api_key/base_url），泛型 K 保证 key/value 类型对应
  const handleDraftFieldChange = useCallback(<K extends keyof ProviderInstance>(key: K, value: ProviderInstance[K]) => {
    setDraftProvider((current) => ({
      ...current,
      [key]: value,
    }))
  }, [])

  // 修改草稿中某个模型的字段（如 display_name/model_name/enabled）
  const handleModelFieldChange = useCallback(<K extends keyof ProviderModel>(
    modelId: string,
    key: K,
    value: ProviderModel[K]
  ) => {
    setDraftProvider((current) => ({
      ...current,
      models: current.models.map((model) => (
        model.id === modelId
          ? {
              ...model,
              [key]: value,
            }
          : model
      )),
    }))
  }, [])

  // 添加一个空白模型：若当前草稿还没有默认模型，则将新模型设为默认
  const handleAddModel = useCallback(() => {
    const nextModel = createEmptyModel()
    setDraftProvider((current) => ({
      ...current,
      models: [...current.models, nextModel],
      default_model_id: current.default_model_id || nextModel.id,
    }))
  }, [])

  // 移除指定模型：若被移除的正是当前默认模型，则回退为剩余列表的第一个模型
  const handleRemoveModel = useCallback((modelId: string) => {
    setDraftProvider((current) => {
      const nextModels = current.models.filter((model) => model.id !== modelId)
      const nextDefaultModelId = nextModels.some((model) => model.id === current.default_model_id)
        ? current.default_model_id
        : nextModels[0]?.id

      return {
        ...current,
        models: nextModels,
        default_model_id: nextDefaultModelId,
      }
    })
  }, [])

  // 保存当前草稿（新建或更新），委托给 providerActions.saveProvider
  const handleSaveProvider = useCallback(async () => {
    await providerActions.saveProvider({
      selectedSavedProvider,
      draftProvider,
    })
  }, [draftProvider, providerActions, selectedSavedProvider])

  // 删除当前选中供应商，删除前通过 dialogService 弹窗二次确认
  const handleDeleteProvider = useCallback(async () => {
    await providerActions.deleteProvider({
      selectedSavedProvider,
      resetDraft,
      confirmDelete: (provider) => dialogService.confirmAction(`确定删除供应商"${provider.name}"吗？`, { variant: 'danger' }),
    })
  }, [dialogService, providerActions, resetDraft, selectedSavedProvider])

  // 测试当前草稿的连接是否可用；成功后用探测到的能力（如是否支持视觉）更新对应模型
  const handleTestConnection = useCallback(async () => {
    const result = await providerActions.testProviderConnection(draftProvider)

    // Update draft with probed capabilities
    if (result?.modelId && result.supports_vision !== undefined) {
      setDraftProvider((current) => ({
        ...current,
        models: current.models.map((model) =>
          model.id === result.modelId
            ? { ...model, supports_vision: result.supports_vision }
            : model
        ),
      }))
    }
  }, [draftProvider, providerActions])

  // 切换默认供应商：联动计算出对应的默认模型（见 providerDraft.applyProviderToDefaultSelection）
  const handleDefaultProviderChange = useCallback((providerId: string) => {
    setDefaultSelection((current) => applyProviderToDefaultSelection(providers, providerId, current))
  }, [providers])

  // 切换默认模型：仅更新 model_id，不影响 provider_id
  const handleDefaultModelChange = useCallback((modelId: string) => {
    setDefaultSelection((current) => ({
      ...current,
      model_id: modelId,
    }))
  }, [])

  // 保存默认模型选择，委托给 providerActions.saveDefaultSelection，成功后同步回本地状态
  const handleSaveDefaultSelection = useCallback(async () => {
    const nextSelection = await providerActions.saveDefaultSelection({
      defaultSelection,
      providers,
    })

    if (nextSelection) {
      setDefaultSelection(nextSelection)
    }
  }, [defaultSelection, providerActions, providers])

  return {
    providers,
    selectedProviderId,
    draftProvider,
    defaultSelection,
    loading,
    saving,
    savingDefault,
    testing,
    savedMessage,
    testResult,
    selectedSavedProvider,
    defaultProviderModels,
    handleSelectProvider,
    handleCreateProvider,
    handleDraftFieldChange,
    handleModelFieldChange,
    handleAddModel,
    handleRemoveModel,
    handleSaveProvider,
    handleDeleteProvider,
    handleTestConnection,
    handleDefaultProviderChange,
    handleDefaultModelChange,
    handleSaveDefaultSelection,
  }
}
