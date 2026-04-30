import { useCallback, useEffect, useMemo, useState } from 'react'
import { nativeDialogService, type DialogService } from '@/services/dialogService'
import type { DefaultLLMSelection, ProviderInstance, ProviderModel } from '@/types/llm'
import {
  applyProviderToDefaultSelection,
  cloneProvider,
  createEmptyModel,
  createEmptyProvider,
  getEnabledModels,
} from './providerDraft'
import {
  createSettingsPageLoader,
  ensureLLMSettingsLoaded,
  resetLLMSettingsStore,
} from './llmSettingsLoader'
import { createSettingsPageActions } from './providerActions'

type TestResult = { type: 'success' | 'error'; message: string } | null

function createEmptySelection(): DefaultLLMSelection {
  return {
    provider_id: null,
    model_id: null,
    configured: false,
  }
}

export function useSettingsPageController(options?: {
  dialogService?: DialogService
  createLoader?: typeof createSettingsPageLoader
  createActions?: typeof createSettingsPageActions
}) {
  const [providers, setProviders] = useState<ProviderInstance[]>([])
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null)
  const [draftProvider, setDraftProvider] = useState<ProviderInstance>(createEmptyProvider())
  const [defaultSelection, setDefaultSelection] = useState<DefaultLLMSelection>(createEmptySelection())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingDefault, setSavingDefault] = useState(false)
  const [testing, setTesting] = useState(false)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<TestResult>(null)

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

  const resetDraft = useCallback(() => {
    setSelectedProviderId(null)
    setDraftProvider(createEmptyProvider())
    setSavedMessage(null)
    setTestResult(null)
  }, [])

  const loadSettings = useMemo(() => (options?.createLoader || createSettingsPageLoader)({
    ensureSettingsLoaded: ensureLLMSettingsLoaded,
    resetStoredSettings: resetLLMSettingsStore,
  }), [options?.createLoader])

  const refreshSettings = useCallback((preferredProviderId?: string | null) => loadSettings({
    preferredProviderId,
    setLoading,
    setProviders,
    setDefaultSelection,
    setSelectedProviderId,
    setDraftProvider,
  }), [loadSettings])

  const dialogService = options?.dialogService || nativeDialogService

  const providerActions = useMemo(() => (options?.createActions || createSettingsPageActions)({
    loadSettings: refreshSettings,
    setSaving,
    setSavingDefault,
    setTesting,
    onSavedMessage: setSavedMessage,
    onTestResult: setTestResult,
    onError: dialogService.notifyError,
  }), [dialogService.notifyError, options?.createActions, refreshSettings])

  useEffect(() => {
    refreshSettings().catch(() => undefined)
  }, [refreshSettings])

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

  const handleCreateProvider = useCallback(() => {
    resetDraft()
  }, [resetDraft])

  const handleDraftFieldChange = useCallback(<K extends keyof ProviderInstance>(key: K, value: ProviderInstance[K]) => {
    setDraftProvider((current) => ({
      ...current,
      [key]: value,
    }))
  }, [])

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

  const handleAddModel = useCallback(() => {
    const nextModel = createEmptyModel()
    setDraftProvider((current) => ({
      ...current,
      models: [...current.models, nextModel],
      default_model_id: current.default_model_id || nextModel.id,
    }))
  }, [])

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

  const handleSaveProvider = useCallback(async () => {
    await providerActions.saveProvider({
      selectedSavedProvider,
      draftProvider,
    })
  }, [draftProvider, providerActions, selectedSavedProvider])

  const handleDeleteProvider = useCallback(async () => {
    await providerActions.deleteProvider({
      selectedSavedProvider,
      resetDraft,
      confirmDelete: (provider) => dialogService.confirmAction(`确定删除供应商“${provider.name}”吗？`),
    })
  }, [dialogService, providerActions, resetDraft, selectedSavedProvider])

  const handleTestConnection = useCallback(async () => {
    await providerActions.testProviderConnection(draftProvider)
  }, [draftProvider, providerActions])

  const handleDefaultProviderChange = useCallback((providerId: string) => {
    setDefaultSelection((current) => applyProviderToDefaultSelection(providers, providerId, current))
  }, [providers])

  const handleDefaultModelChange = useCallback((modelId: string) => {
    setDefaultSelection((current) => ({
      ...current,
      model_id: modelId,
    }))
  }, [])

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
