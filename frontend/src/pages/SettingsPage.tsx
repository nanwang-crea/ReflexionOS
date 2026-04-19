import { useEffect, useMemo, useState } from 'react'
import { llmApi } from '@/services/apiClient'
import { useSettingsStore } from '@/stores/settingsStore'
import type { DefaultLLMSelection, ProviderInstance, ProviderModel, ProviderType } from '@/types/llm'

const providerTypeOptions: Array<{ value: ProviderType; label: string }> = [
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
]

function createLocalId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEmptyModel(): ProviderModel {
  return {
    id: createLocalId('model'),
    display_name: '',
    model_name: '',
    enabled: true,
  }
}

function createEmptyProvider(): ProviderInstance {
  const model = createEmptyModel()

  return {
    id: createLocalId('provider'),
    name: '',
    provider_type: 'openai_compatible',
    api_key: '',
    base_url: '',
    models: [model],
    default_model_id: model.id,
    enabled: true,
  }
}

function cloneProvider(provider: ProviderInstance): ProviderInstance {
  return {
    ...provider,
    models: provider.models.map((model) => ({ ...model })),
  }
}

function getEnabledModels(provider: ProviderInstance | null | undefined) {
  return provider?.models.filter((model) => model.enabled) || []
}

function normalizeProviderDraft(provider: ProviderInstance): ProviderInstance {
  const models = provider.models.map((model) => ({
    ...model,
    display_name: model.display_name.trim(),
    model_name: model.model_name.trim(),
  }))
  const defaultModelId = models.some((model) => model.id === provider.default_model_id)
    ? provider.default_model_id
    : models[0]?.id

  return {
    ...provider,
    name: provider.name.trim(),
    api_key: provider.api_key?.trim() || undefined,
    base_url: provider.base_url?.trim() || undefined,
    models,
    default_model_id: defaultModelId,
  }
}

function validateProviderDraft(provider: ProviderInstance) {
  if (!provider.name.trim()) {
    return '供应商名称不能为空'
  }

  if (provider.models.length === 0) {
    return '请至少配置一个模型'
  }

  const hasEmptyModel = provider.models.some((model) => (
    !model.display_name.trim() || !model.model_name.trim()
  ))
  if (hasEmptyModel) {
    return '模型显示名称和模型名称不能为空'
  }

  return null
}

export default function SettingsPage() {
  const { setLLMState } = useSettingsStore()
  const [providers, setProviders] = useState<ProviderInstance[]>([])
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null)
  const [draftProvider, setDraftProvider] = useState<ProviderInstance>(createEmptyProvider())
  const [defaultSelection, setDefaultSelection] = useState<DefaultLLMSelection>({
    provider_id: null,
    model_id: null,
    configured: false,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingDefault, setSavingDefault] = useState(false)
  const [testing, setTesting] = useState(false)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

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

  const loadSettings = async (preferredProviderId?: string | null) => {
    setLoading(true)

    try {
      const [providersResponse, defaultResponse] = await Promise.all([
        llmApi.getProviders(),
        llmApi.getDefaultSelection(),
      ])

      const nextProviders = providersResponse.data
      const nextSelection = defaultResponse.data

      setProviders(nextProviders)
      setDefaultSelection(nextSelection)
      setLLMState({
        providers: nextProviders,
        selection: nextSelection,
      })

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
      setProviders([])
      setDefaultSelection({
        provider_id: null,
        model_id: null,
        configured: false,
      })
      setLLMState({
        providers: [],
        selection: {
          provider_id: null,
          model_id: null,
          configured: false,
        },
      })
      setSelectedProviderId(null)
      setDraftProvider(createEmptyProvider())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSettings()
  }, [])

  const handleSelectProvider = (providerId: string) => {
    const provider = providers.find((item) => item.id === providerId)
    if (!provider) {
      return
    }

    setSelectedProviderId(providerId)
    setDraftProvider(cloneProvider(provider))
    setSavedMessage(null)
    setTestResult(null)
  }

  const handleCreateProvider = () => {
    setSelectedProviderId(null)
    setDraftProvider(createEmptyProvider())
    setSavedMessage(null)
    setTestResult(null)
  }

  const handleDraftFieldChange = <K extends keyof ProviderInstance>(key: K, value: ProviderInstance[K]) => {
    setDraftProvider((current) => ({
      ...current,
      [key]: value,
    }))
  }

  const handleModelFieldChange = <K extends keyof ProviderModel>(
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
  }

  const handleAddModel = () => {
    const nextModel = createEmptyModel()
    setDraftProvider((current) => ({
      ...current,
      models: [...current.models, nextModel],
      default_model_id: current.default_model_id || nextModel.id,
    }))
  }

  const handleRemoveModel = (modelId: string) => {
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
  }

  const handleSaveProvider = async () => {
    const validationError = validateProviderDraft(draftProvider)
    if (validationError) {
      alert(validationError)
      return
    }

    const payload = normalizeProviderDraft(draftProvider)
    setSaving(true)
    setSavedMessage(null)

    try {
      if (selectedSavedProvider) {
        await llmApi.updateProvider(selectedSavedProvider.id, payload)
      } else {
        await llmApi.createProvider(payload)
      }

      await loadSettings(payload.id)
      setSavedMessage('供应商已保存')
    } catch (error: any) {
      console.error('Failed to save provider:', error)
      alert(error.response?.data?.detail || '保存供应商失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteProvider = async () => {
    if (!selectedSavedProvider) {
      handleCreateProvider()
      return
    }

    const shouldDelete = confirm(`确定删除供应商“${selectedSavedProvider.name}”吗？`)
    if (!shouldDelete) {
      return
    }

    try {
      await llmApi.deleteProvider(selectedSavedProvider.id)
      await loadSettings()
      setSavedMessage('供应商已删除')
    } catch (error: any) {
      console.error('Failed to delete provider:', error)
      alert(error.response?.data?.detail || '删除供应商失败')
    }
  }

  const handleTestConnection = async () => {
    const validationError = validateProviderDraft(draftProvider)
    if (validationError) {
      setTestResult({ type: 'error', message: validationError })
      return
    }

    const payload = normalizeProviderDraft(draftProvider)
    const modelId = payload.default_model_id || payload.models[0]?.id || null
    if (!modelId) {
      setTestResult({ type: 'error', message: '请先至少配置一个模型' })
      return
    }

    setTesting(true)
    setTestResult(null)

    try {
      const response = await llmApi.testProvider({
        provider: payload,
        model_id: modelId,
      })
      setTestResult({
        type: 'success',
        message: `${response.data.message}，模型：${response.data.model}`,
      })
    } catch (error: any) {
      console.error('Failed to test provider connection:', error)
      setTestResult({
        type: 'error',
        message: error.response?.data?.detail || '连接测试失败',
      })
    } finally {
      setTesting(false)
    }
  }

  const handleDefaultProviderChange = (providerId: string) => {
    const provider = providers.find((item) => item.id === providerId) || null
    const models = getEnabledModels(provider)
    setDefaultSelection((current) => ({
      ...current,
      provider_id: providerId,
      model_id: models.find((model) => model.id === provider?.default_model_id)?.id || models[0]?.id || null,
    }))
  }

  const handleSaveDefaultSelection = async () => {
    if (!defaultSelection.provider_id || !defaultSelection.model_id) {
      alert('请选择默认供应商和默认模型')
      return
    }

    setSavingDefault(true)
    setSavedMessage(null)

    try {
      const response = await llmApi.setDefaultSelection({
        provider_id: defaultSelection.provider_id,
        model_id: defaultSelection.model_id,
      })

      setDefaultSelection(response.data)
      setLLMState({
        providers,
        selection: response.data,
      })
      setSavedMessage('默认模型已保存')
    } catch (error: any) {
      console.error('Failed to save default selection:', error)
      alert(error.response?.data?.detail || '保存默认模型失败')
    } finally {
      setSavingDefault(false)
    }
  }

  return (
    <div className="p-8">
      <h2 className="mb-6 text-2xl font-bold text-gray-900">Settings</h2>

      <div className="grid gap-6 xl:grid-cols-[280px,minmax(0,1fr)]">
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">供应商实例</h3>
            <button
              onClick={handleCreateProvider}
              className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              新增供应商
            </button>
          </div>

          <div className="space-y-2">
            {loading && (
              <div className="rounded-lg bg-gray-50 px-3 py-4 text-sm text-gray-500">
                正在加载配置...
              </div>
            )}

            {!loading && providers.length === 0 && (
              <div className="rounded-lg bg-gray-50 px-3 py-4 text-sm text-gray-500">
                还没有供应商配置，可以先新增一个。
              </div>
            )}

            {providers.map((provider) => (
              <button
                key={provider.id}
                type="button"
                onClick={() => handleSelectProvider(provider.id)}
                className={`w-full rounded-lg border px-3 py-3 text-left transition ${
                  selectedProviderId === provider.id
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <div className="font-medium text-gray-900">{provider.name}</div>
                <div className="mt-1 text-sm text-gray-500">
                  {providerTypeOptions.find((item) => item.value === provider.provider_type)?.label}
                </div>
                <div className="mt-1 text-xs text-gray-400">
                  {provider.models.length} 个模型
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">
                {selectedSavedProvider ? '编辑供应商' : '新建供应商'}
              </h3>
              {savedMessage && (
                <span className="text-sm text-green-600">{savedMessage}</span>
              )}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  名称
                </label>
                <input
                  type="text"
                  value={draftProvider.name}
                  onChange={(e) => handleDraftFieldChange('name', e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2"
                  placeholder="例如：OpenAI 官方"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  协议类型
                </label>
                <select
                  value={draftProvider.provider_type}
                  onChange={(e) => handleDraftFieldChange('provider_type', e.target.value as ProviderType)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2"
                >
                  {providerTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Base URL
                </label>
                <input
                  type="text"
                  value={draftProvider.base_url || ''}
                  onChange={(e) => handleDraftFieldChange('base_url', e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2"
                  placeholder="https://api.openai.com/v1"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  API Key
                </label>
                <input
                  type="password"
                  value={draftProvider.api_key || ''}
                  onChange={(e) => handleDraftFieldChange('api_key', e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2"
                  placeholder="sk-..."
                />
              </div>
            </div>

            <div className="mt-6">
              <div className="mb-3 flex items-center justify-between">
                <h4 className="text-sm font-semibold text-gray-900">模型列表</h4>
                <button
                  type="button"
                  onClick={handleAddModel}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  新增模型
                </button>
              </div>

              <div className="space-y-3">
                {draftProvider.models.map((model) => (
                  <div key={model.id} className="rounded-lg border border-gray-200 p-4">
                    <div className="grid gap-3 md:grid-cols-[1fr,1fr,auto,auto]">
                      <input
                        type="text"
                        value={model.display_name}
                        onChange={(e) => handleModelFieldChange(model.id, 'display_name', e.target.value)}
                        className="rounded-lg border border-gray-300 px-3 py-2"
                        placeholder="显示名称，例如 GPT-4.1"
                      />
                      <input
                        type="text"
                        value={model.model_name}
                        onChange={(e) => handleModelFieldChange(model.id, 'model_name', e.target.value)}
                        className="rounded-lg border border-gray-300 px-3 py-2"
                        placeholder="模型名称，例如 gpt-4.1"
                      />
                      <label className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700">
                        <input
                          type="checkbox"
                          checked={model.enabled}
                          onChange={(e) => handleModelFieldChange(model.id, 'enabled', e.target.checked)}
                        />
                        启用
                      </label>
                      <button
                        type="button"
                        onClick={() => handleRemoveModel(model.id)}
                        disabled={draftProvider.models.length === 1}
                        className="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-6 max-w-sm">
              <label className="mb-1 block text-sm font-medium text-gray-700">
                供应商默认模型
              </label>
              <select
                value={draftProvider.default_model_id || ''}
                onChange={(e) => handleDraftFieldChange('default_model_id', e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2"
              >
                {draftProvider.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name || model.model_name || '未命名模型'}
                  </option>
                ))}
              </select>
            </div>

            {testResult && (
              <div
                className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
                  testResult.type === 'success'
                    ? 'border-green-200 bg-green-50 text-green-700'
                    : 'border-red-200 bg-red-50 text-red-700'
                }`}
              >
                {testResult.message}
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <button
                onClick={handleTestConnection}
                disabled={testing}
                className={`rounded-lg px-4 py-2 ${
                  testing
                    ? 'bg-gray-300 text-gray-500'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {testing ? '测试中...' : '测试连接'}
              </button>
              <button
                onClick={handleSaveProvider}
                disabled={saving}
                className={`rounded-lg px-4 py-2 ${
                  saving
                    ? 'bg-gray-300 text-gray-500'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                }`}
              >
                {saving ? '保存中...' : '保存供应商'}
              </button>
              <button
                onClick={handleDeleteProvider}
                className="rounded-lg border border-red-200 px-4 py-2 text-red-600 hover:bg-red-50"
              >
                {selectedSavedProvider ? '删除供应商' : '清空草稿'}
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">全局默认模型</h3>

            {providers.length === 0 ? (
              <div className="rounded-lg bg-gray-50 px-4 py-4 text-sm text-gray-500">
                先保存至少一个供应商，才能设置默认模型。
              </div>
            ) : (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      默认供应商
                    </label>
                    <select
                      value={defaultSelection.provider_id || ''}
                      onChange={(e) => handleDefaultProviderChange(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    >
                      {providers.map((provider) => (
                        <option key={provider.id} value={provider.id}>
                          {provider.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      默认模型
                    </label>
                    <select
                      value={defaultSelection.model_id || ''}
                      onChange={(e) => setDefaultSelection((current) => ({
                        ...current,
                        model_id: e.target.value,
                      }))}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2"
                    >
                      {defaultProviderModels.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.display_name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-4 flex items-center gap-3">
                  <button
                    onClick={handleSaveDefaultSelection}
                    disabled={savingDefault}
                    className={`rounded-lg px-4 py-2 ${
                      savingDefault
                        ? 'bg-gray-300 text-gray-500'
                        : 'bg-blue-600 text-white hover:bg-blue-700'
                    }`}
                  >
                    {savingDefault ? '保存中...' : '保存默认模型'}
                  </button>
                  {defaultSelection.configured ? (
                    <span className="text-sm text-green-600">默认模型已就绪</span>
                  ) : (
                    <span className="text-sm text-amber-600">当前尚未形成可执行的默认配置</span>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">关于</h3>
            <p className="text-gray-600">
              ReflexionOS 是一个 AI-powered coding agent。本页现在支持维护多个供应商实例，
              并为聊天页提供默认模型和连接测试能力。
            </p>
            <p className="mt-2 text-sm text-gray-500">Version 0.1.0</p>
          </div>
        </div>
      </div>
    </div>
  )
}
