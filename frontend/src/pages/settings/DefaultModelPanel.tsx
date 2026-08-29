/**
 * 文件功能：设置页“全局默认模型”面板组件
 * 文件描述：让用户从已配置的供应商中选择一个默认供应商及默认模型，作为全局对话的默认使用配置
 * 核心逻辑：状态与操作逻辑集中在 useSettingsPageController 这个 hook 中，本组件只负责渲染 UI
 *          和转发用户交互事件；面板会根据是否已有供应商决定展示选择器还是提示信息
 */
import { useSettingsPageController } from '@/features/llm/useSettingsPageController'

/**
 * 函数名：DefaultModelPanel
 * 入参：无
 * 功能：渲染“全局默认模型”设置面板，支持选择默认供应商和默认模型并保存
 * 运行逻辑：
 *   1. 通过 useSettingsPageController 获取供应商列表、当前默认选择、保存状态及各类回调
 *   2. 根据 defaultSelection.provider_id 找到对应供应商，过滤出该供应商下已启用的模型列表
 *   3. 若尚无任何供应商，展示提示文案；否则渲染供应商/模型下拉选择框和保存按钮
 *   4. 保存后根据 defaultSelection.configured 状态展示“已就绪”或“未配置完整”的提示
 * 出参：JSX.Element - 全局默认模型设置面板的 DOM 结构
 */
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
