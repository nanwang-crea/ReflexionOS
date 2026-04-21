import { useSettingsPageController } from '@/features/llm/useSettingsPageController'
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
  } = useSettingsPageController({ onError: (message) => alert(message) })

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
                 onClick={() => { void handleTestConnection() }}
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
                  onClick={() => { void handleSaveProvider() }}
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
                  onClick={() => { void handleDeleteProvider() }}
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
                       onChange={(e) => handleDefaultModelChange(e.target.value)}
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
                     onClick={() => { void handleSaveDefaultSelection() }}
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
