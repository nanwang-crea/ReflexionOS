/**
 * 文件功能：设置页“供应商实例”管理面板组件
 * 文件描述：提供 LLM 供应商实例的新增/编辑/删除/测试连接功能，并管理每个供应商下的模型列表
 *          （新增/删除模型、编辑模型显示名/模型名/启用状态/视觉能力）以及默认模型选择
 * 核心逻辑：状态与业务逻辑集中在 useSettingsPageController 这个 hook 中，本组件只负责渲染 UI
 *          布局（左侧供应商列表 + 右侧编辑表单）并转发用户交互事件到 hook 提供的回调
 */
import { useState } from 'react'
import { useSettingsPageController } from '@/features/llm/useSettingsPageController'
import type { ProviderType } from '@/types/llm'

/** 供应商协议类型下拉选项列表：值与后端 ProviderType 对应，标签为界面展示文案 */
const providerTypeOptions: Array<{ value: ProviderType; label: string }> = [
  { value: 'openai_compatible', label: 'OpenAI Compatible' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
]

/**
 * 函数名：ProviderPanel
 * 入参：无
 * 功能：渲染供应商实例管理面板，包括左侧供应商列表和右侧新建/编辑表单
 * 运行逻辑：
 *   1. 通过 useSettingsPageController 获取供应商列表、当前选中项、草稿数据、各类加载/保存/测试状态及操作回调
 *   2. 左侧栏渲染供应商列表，支持点击切换选中项、新增供应商按钮
 *   3. 右侧栏渲染草稿供应商的表单字段（名称、协议类型、Base URL、API Key）
 *   4. 右侧栏渲染该供应商下的模型列表，支持新增/删除模型、编辑模型字段（显示名、模型名、启用状态），
 *      并展示每个模型的视觉能力（Vision）标识
 *   5. 渲染默认模型下拉框、连接测试结果提示，以及测试连接/保存供应商/删除供应商（或清空草稿）按钮
 * 出参：JSX.Element - 供应商管理面板的 DOM 结构
 */
export function ProviderPanel() {
  const {
    providers,
    selectedProviderId,
    draftProvider,
    loading,
    saving,
    testing,
    savedMessage,
    testResult,
    selectedSavedProvider,
    fetchingRemoteModels,
    remoteModels,
    showImportModal,
    handleSelectProvider,
    handleCreateProvider,
    handleDraftFieldChange,
    handleModelFieldChange,
    handleAddModel,
    handleRemoveModel,
    handleSaveProvider,
    handleDeleteProvider,
    handleTestConnection,
    handleFetchRemoteModels,
    handleImportRemoteModels,
    handleCloseImportModal,
  } = useSettingsPageController()

  // 导入对话框内勾选的远端模型 id 集合（本地 UI 状态，关闭时清空）
  const [selectedRemoteIds, setSelectedRemoteIds] = useState<Set<string>>(new Set())

  // 切换某行勾选；支持全选/取消全选
  const toggleRemoteId = (id: string) => {
    setSelectedRemoteIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }
  const toggleAllRemote = () => {
    setSelectedRemoteIds((prev) =>
      prev.size === remoteModels.length ? new Set() : new Set(remoteModels.map((m) => m.id))
    )
  }
  // 导入对话框关闭时清空勾选
  const closeImportModal = () => {
    setSelectedRemoteIds(new Set())
    handleCloseImportModal()
  }
  // 确认导入：把勾选的远端模型交给 controller 去重导入
  const confirmImport = () => {
    const selected = remoteModels.filter((m) => selectedRemoteIds.has(m.id))
    handleImportRemoteModels(selected)
    setSelectedRemoteIds(new Set())
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[280px,minmax(0,1fr)]">
        <div className="rounded-lg border border-edge bg-surface-primary p-4">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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

        <div className="rounded-lg border border-edge bg-surface-primary p-4 sm:p-6">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-lg font-semibold text-content-primary">
              {selectedSavedProvider ? '编辑供应商' : '新建供应商'}
            </h3>
            {savedMessage && (
              <span className="text-sm text-status-success">{savedMessage}</span>
            )}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-content-secondary">名称</label>
              <input
                type="text"
                value={draftProvider.name}
                onChange={(e) => handleDraftFieldChange('name', e.target.value)}
                className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                placeholder="例如：OpenAI 官方"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-content-secondary">协议类型</label>
              <select
                value={draftProvider.provider_type}
                onChange={(e) => {
                  const val = e.target.value
                  if (val === 'openai_compatible' || val === 'anthropic' || val === 'ollama') {
                    handleDraftFieldChange('provider_type', val)
                  }
                }}
                className="w-full rounded-lg border border-edge bg-surface-primary px-3 py-2 text-sm text-content-primary"
              >
                {providerTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-content-secondary">Base URL</label>
              <input
                type="text"
                value={draftProvider.base_url || ''}
                onChange={(e) => handleDraftFieldChange('base_url', e.target.value)}
                className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                placeholder="https://api.openai.com/v1"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-content-secondary">API Key</label>
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
            <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h4 className="text-sm font-semibold text-content-primary">模型列表</h4>
              <div className="flex flex-wrap gap-2">
                {/* 获取远端可用模型：调后端 GET /v1/models，拉回后弹出导入对话框。
                    仅 OpenAI 兼容供应商可用；需先填好 base_url + api_key */}
                <button
                  type="button"
                  onClick={() => { void handleFetchRemoteModels() }}
                  disabled={
                    fetchingRemoteModels
                    || draftProvider.provider_type !== 'openai_compatible'
                    || !draftProvider.base_url
                    || !draftProvider.api_key
                  }
                  className="rounded-lg border border-edge px-3 py-2 text-sm text-content-secondary hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:text-content-muted"
                  title={
                    draftProvider.provider_type !== 'openai_compatible'
                      ? '当前仅支持 OpenAI 兼容供应商'
                      : !draftProvider.base_url || !draftProvider.api_key
                        ? '请先填写 Base URL 和 API Key'
                        : '从 API 站点拉取可用模型列表'
                  }
                >
                  {fetchingRemoteModels ? '获取中...' : '获取可用模型'}
                </button>
                <button
                  type="button"
                  onClick={handleAddModel}
                  className="rounded-lg border border-edge px-3 py-2 text-sm text-content-secondary hover:bg-surface-tertiary"
                >
                  新增模型
                </button>
              </div>
            </div>

            <div className="max-h-[50vh] space-y-3 overflow-y-auto">
              {draftProvider.models.map((model) => (
                <div key={model.id} className="rounded-lg border border-edge p-4">
                  <div className="grid gap-3 sm:grid-cols-[1fr,1fr] lg:grid-cols-[1fr,1fr,auto,auto]">
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

                  {/* Capability indicators */}
                  <div className="mt-2 flex gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      model.supports_vision === true
                        ? 'bg-status-success-soft text-status-success'
                        : model.supports_vision === false
                        ? 'bg-status-error-soft text-status-error'
                        : 'bg-surface-tertiary text-content-muted'
                    }`}>
                      Vision: {
                        model.supports_vision === true ? 'Enabled'
                        : model.supports_vision === false ? 'Disabled'
                        : 'Auto'
                      }
                    </span>
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

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
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
      </div>

      {/* 导入远端模型对话框：多选列表 + 导入选中按钮。
          已存在的模型导入时按 model_name 去重（见 controller handleImportRemoteModels） */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="max-h-[80vh] w-full max-w-2xl overflow-hidden rounded-lg border border-edge bg-surface-primary shadow-lg">
            <div className="flex items-center justify-between border-b border-edge px-4 py-3">
              <h3 className="text-base font-semibold text-content-primary">
                可用模型（共 {remoteModels.length} 个）
              </h3>
              <button
                type="button"
                onClick={closeImportModal}
                className="text-content-muted hover:text-content-primary"
              >
                ✕
              </button>
            </div>

            <div className="max-h-[55vh] overflow-y-auto px-4 py-2">
              {remoteModels.length === 0 ? (
                <div className="px-3 py-6 text-sm text-content-muted">
                  站点未返回任何模型
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="flex items-center gap-2 border-b border-edge py-2 text-sm text-content-secondary">
                    <input
                      type="checkbox"
                      checked={selectedRemoteIds.size === remoteModels.length && remoteModels.length > 0}
                      onChange={toggleAllRemote}
                    />
                    全选 / 取消全选
                  </label>
                  {remoteModels.map((model) => (
                    <label
                      key={model.id}
                      className="flex items-center gap-2 rounded px-2 py-1.5 text-sm text-content-secondary hover:bg-surface-tertiary"
                    >
                      <input
                        type="checkbox"
                        checked={selectedRemoteIds.has(model.id)}
                        onChange={() => toggleRemoteId(model.id)}
                      />
                      <span className="font-mono">{model.id}</span>
                      {model.owned_by && (
                        <span className="text-xs text-content-muted">（{model.owned_by}）</span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-edge px-4 py-3">
              <button
                type="button"
                onClick={closeImportModal}
                className="rounded-lg border border-edge px-4 py-2 text-sm text-content-secondary hover:bg-surface-tertiary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmImport}
                disabled={selectedRemoteIds.size === 0}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
              >
                导入选中（{selectedRemoteIds.size}）
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
