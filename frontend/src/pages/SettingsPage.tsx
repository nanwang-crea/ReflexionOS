import { useCallback, useEffect } from 'react'
import { useSettingsPageController } from '@/features/llm/useSettingsPageController'
import { uiSettingsApi } from '@/services/apiClient'
import { useSettingsStore } from '@/stores/settingsStore'
import { useToastStore } from '@/stores/toastStore'
import type { ProviderType } from '@/types/llm'

const providerTypeOptions: Array<{ value: ProviderType; label: string }> = [
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
]

export default function SettingsPage() {
  const {
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
  } = useSettingsPageController()

  const showContinuationNotices = useSettingsStore((s) => s.showContinuationNotices)
  const uiSettingsLoaded = useSettingsStore((s) => s.uiSettingsLoaded)
  const setUISetting = useSettingsStore((s) => s.setUISetting)

  useEffect(() => {
    if (uiSettingsLoaded) return
    uiSettingsApi.get()
      .then((res) => {
        setUISetting({ showContinuationNotices: res.data.show_continuation_notices })
      })
      .catch(() => {
        useToastStore.getState().addToast('error', '加载 UI 设置失败')
      })
  }, [uiSettingsLoaded, setUISetting])

  const handleToggleContinuationNotices = useCallback(async () => {
    const next = !showContinuationNotices
    try {
      await uiSettingsApi.update({ show_continuation_notices: next })
      setUISetting({ showContinuationNotices: next })
    } catch {
      useToastStore.getState().addToast('error', '保存 UI 设置失败')
    }
  }, [showContinuationNotices, setUISetting])

  return (
    <div className="h-full overflow-y-auto bg-surface-primary">
      <div className="mx-auto max-w-5xl px-10 py-10">
      <h2 className="mb-6 text-2xl font-bold text-content-primary">Settings</h2>

      <div className="grid gap-6 xl:grid-cols-[280px,minmax(0,1fr)]">
        <div className="rounded-lg border border-edge bg-surface-primary p-4">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-content-primary">供应商实例</h3>
            <button
              onClick={handleCreateProvider}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover"
            >
              新增供应商
            </button>
          </div>

          <div className="space-y-2">
            {loading && (
              <div className="rounded-lg bg-surface-tertiary px-3 py-4 text-sm text-content-muted">
                正在加载配置...
              </div>
            )}

            {!loading && providers.length === 0 && (
              <div className="rounded-lg bg-surface-tertiary px-3 py-4 text-sm text-content-muted">
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
                    ? 'border-accent bg-accent-soft'
                    : 'border-edge hover:bg-surface-tertiary'
                }`}
              >
                <div className="font-medium text-content-primary">{provider.name}</div>
                <div className="mt-1 text-sm text-content-muted">
                  {providerTypeOptions.find((item) => item.value === provider.provider_type)?.label}
                </div>
                <div className="mt-1 text-xs text-content-muted">
                  {provider.models.length} 个模型
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-lg border border-edge bg-surface-primary p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-content-primary">
                {selectedSavedProvider ? '编辑供应商' : '新建供应商'}
              </h3>
                {savedMessage && (
                  <span className="text-sm text-status-success">{savedMessage}</span>
                )}
              </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-content-secondary">
                  名称
                </label>
                <input
                  type="text"
                  value={draftProvider.name}
                  onChange={(e) => handleDraftFieldChange('name', e.target.value)}
                  className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                  placeholder="例如：OpenAI 官方"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-content-secondary">
                  协议类型
                </label>
                <select
                  value={draftProvider.provider_type}
                  onChange={(e) => handleDraftFieldChange('provider_type', e.target.value as ProviderType)}
                  className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                >
                  {providerTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-content-secondary">
                  Base URL
                </label>
                <input
                  type="text"
                  value={draftProvider.base_url || ''}
                  onChange={(e) => handleDraftFieldChange('base_url', e.target.value)}
                  className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                  placeholder="https://api.openai.com/v1"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-content-secondary">
                  API Key
                </label>
                <input
                  type="password"
                  value={draftProvider.api_key || ''}
                  onChange={(e) => handleDraftFieldChange('api_key', e.target.value)}
                  className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                  placeholder="sk-..."
                />
              </div>
            </div>

            <div className="mt-6">
              <div className="mb-3 flex items-center justify-between">
                <h4 className="text-sm font-semibold text-content-primary">模型列表</h4>
                <button
                  type="button"
                  onClick={handleAddModel}
                  className="rounded-lg border border-edge px-3 py-2 text-sm text-content-secondary hover:bg-surface-tertiary"
                >
                  新增模型
                </button>
              </div>

              <div className="max-h-[50vh] space-y-3 overflow-y-auto">
                {draftProvider.models.map((model) => (
                  <div key={model.id} className="rounded-lg border border-edge p-4">
                    <div className="grid gap-3 sm:grid-cols-[1fr,1fr] md:grid-cols-[1fr,1fr,auto,auto]">
                      <input
                        type="text"
                        value={model.display_name}
                        onChange={(e) => handleModelFieldChange(model.id, 'display_name', e.target.value)}
                        className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                        placeholder="显示名称，例如 GPT-4.1"
                      />
                      <input
                        type="text"
                        value={model.model_name}
                        onChange={(e) => handleModelFieldChange(model.id, 'model_name', e.target.value)}
                        className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                        placeholder="模型名称，例如 gpt-4.1"
                      />
                      <label className="flex items-center gap-2 rounded-lg border border-edge px-3 py-2 text-sm text-content-secondary">
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
                        className="rounded-lg border border-status-error-border px-3 py-2 text-sm text-status-error hover:bg-status-error-soft disabled:cursor-not-allowed disabled:border-edge disabled:text-content-muted"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-6 max-w-sm">
              <label className="mb-1 block text-sm font-medium text-content-secondary">
                供应商默认模型
              </label>
              <select
                 value={draftProvider.default_model_id || ''}
                 onChange={(e) => handleDraftFieldChange('default_model_id', e.target.value)}
                className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
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
                       ? 'border-status-success-border bg-status-success-soft text-status-success'
                       : 'border-status-error-border bg-status-error-soft text-status-error'
                  }`}
                >
                  {testResult.message}
                </div>
              )}

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <button
                 onClick={() => { void handleTestConnection() }}
                 disabled={testing}
                 className={`rounded-lg px-4 py-2 ${
                   testing
                      ? 'bg-surface-tertiary text-content-muted'
                      : 'bg-surface-tertiary text-content-secondary hover:bg-surface-tertiary'
                  }`}
                >
                  {testing ? '测试中...' : '测试连接'}
                </button>
                <button
                  onClick={() => { void handleSaveProvider() }}
                  disabled={saving}
                  className={`rounded-lg px-4 py-2 ${
                   saving
                      ? 'bg-surface-tertiary text-content-muted'
                      : 'bg-accent text-white hover:bg-accent-hover'
                  }`}
                >
                  {saving ? '保存中...' : '保存供应商'}
                </button>
                <button
                  onClick={() => { void handleDeleteProvider() }}
                  className="rounded-lg border border-status-error-border px-4 py-2 text-status-error hover:bg-status-error-soft"
                >
                 {selectedSavedProvider ? '删除供应商' : '清空草稿'}
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-edge bg-surface-primary p-6">
            <h3 className="mb-4 text-lg font-semibold text-content-primary">全局默认模型</h3>

             {providers.length === 0 ? (
              <div className="rounded-lg bg-surface-tertiary px-4 py-4 text-sm text-content-muted">
                先保存至少一个供应商，才能设置默认模型。
              </div>
            ) : (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-content-secondary">
                      默认供应商
                    </label>
                    <select
                       value={defaultSelection.provider_id || ''}
                       onChange={(e) => handleDefaultProviderChange(e.target.value)}
                       className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                     >
                       {providers.map((provider) => (
                        <option key={provider.id} value={provider.id}>
                          {provider.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium text-content-secondary">
                      默认模型
                    </label>
                    <select
                       value={defaultSelection.model_id || ''}
                       onChange={(e) => handleDefaultModelChange(e.target.value)}
                       className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
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
                     onClick={() => { void handleSaveDefaultSelection() }}
                     disabled={savingDefault}
                     className={`rounded-lg px-4 py-2 ${
                       savingDefault
                          ? 'bg-surface-tertiary text-content-muted'
                          : 'bg-accent text-white hover:bg-accent-hover'
                      }`}
                    >
                     {savingDefault ? '保存中...' : '保存默认模型'}
                    </button>
                    {defaultSelection.configured ? (
                      <span className="text-sm text-status-success">默认模型已就绪</span>
                    ) : (
                    <span className="text-sm text-status-warning">当前尚未形成可执行的默认配置</span>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="rounded-lg border border-edge bg-surface-primary p-6">
            <h3 className="mb-4 text-lg font-semibold text-content-primary">显示选项</h3>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-content-secondary">显示延续摘要通知</p>
                <p className="mt-1 text-sm text-content-muted">
                  开启后，对话上下文压缩时会在聊天中显示摘要通知
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={showContinuationNotices}
                onClick={() => { void handleToggleContinuationNotices() }}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 ${
                  showContinuationNotices ? 'bg-accent' : 'bg-surface-tertiary'
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    showContinuationNotices ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-edge bg-surface-primary p-6">
            <p className="text-content-secondary">
              ReflexionOS 是一个 AI-powered coding agent。本页现在支持维护多个供应商实例，
              并为聊天页提供默认模型和连接测试能力。
            </p>
            <p className="mt-2 text-sm text-content-muted">Version 0.1.0</p>
          </div>
        </div>
       </div>
      </div>
    </div>
   )
}
