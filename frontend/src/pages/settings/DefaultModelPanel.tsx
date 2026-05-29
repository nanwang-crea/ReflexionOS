import { useSettingsPageController } from '@/features/llm/useSettingsPageController'

export function DefaultModelPanel() {
  const {
    providers,
    defaultSelection,
    savingDefault,
    handleDefaultProviderChange,
    handleDefaultModelChange,
    handleSaveDefaultSelection,
  } = useSettingsPageController()

  const defaultProvider = providers.find((p) => p.id === defaultSelection.provider_id) || null
  const defaultProviderModels = defaultProvider
    ? defaultProvider.models.filter((m) => m.enabled)
    : []

  return (
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
  )
}
