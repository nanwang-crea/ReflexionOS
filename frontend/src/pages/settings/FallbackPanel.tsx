/**
 * 文件功能：设置页"运行兜底"面板组件
 * 文件描述：配置主模型超时后按顺序尝试的备用模型链，以及主 run 的墙钟超时秒数。
 *           主模型超时 → 备用1 → 备用2 → ... → 全部失败输出"当前无可用模型"。
 * 核心逻辑：独立面板，直接调 llmApi.getRuntimeSettings/updateRuntimeSettings 读写，
 *          不走 useSettingsPageController（那个是供应商 CRUD 用的）；用 useSettingsStore 拿 providers 列表。
 */
import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { llmApi } from '@/features/llm/api/llm.api'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import { useToastStore } from '@/shared/stores/toast.store'
import type { FallbackModelEntry, RuntimeSettings } from '@/types/llm'

const DEFAULT_SETTINGS: RuntimeSettings = {
  fallback_chain: [],
  run_timeout_seconds: 600,
}

/**
 * 函数名：FallbackPanel
 * 入参：无
 * 功能：渲染运行兜底设置面板，支持增删备用模型链条目 + 超时秒数并保存
 * 运行逻辑：
 *   1. 从 useSettingsStore 取已启用供应商列表（用于下拉）
 *   2. 挂载时调 llmApi.getRuntimeSettings 加载当前兜底配置
 *   3. 备用链每行：供应商 select + 模型 select + 删除按钮；底部"添加备用"按钮
 *   4. 保存调 llmApi.updateRuntimeSettings，成功 toast 提示
 * 出参：JSX.Element - 运行兜底设置面板
 */
export function FallbackPanel() {
  const providers = useSettingsStore((s) => s.providers).filter((p) => p.enabled)
  const [settings, setSettings] = useState<RuntimeSettings>(DEFAULT_SETTINGS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // 挂载时加载当前兜底配置
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    llmApi.getRuntimeSettings()
      .then((loaded) => {
        if (!cancelled) setSettings(loaded)
      })
      .catch((error) => {
        console.error('Failed to load runtime settings:', error)
        useToastStore.getState().addToast('error', '加载兜底配置失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  // 添加一个空白备用条目
  const handleAddEntry = useCallback(() => {
    setSettings((prev) => ({
      ...prev,
      fallback_chain: [...prev.fallback_chain, { provider_id: '', model_id: '' }],
    }))
  }, [])

  // 删除指定索引的条目
  const handleRemoveEntry = useCallback((index: number) => {
    setSettings((prev) => ({
      ...prev,
      fallback_chain: prev.fallback_chain.filter((_, i) => i !== index),
    }))
  }, [])

  // 修改指定条目的供应商（联动清空模型）
  const handleEntryProviderChange = useCallback((index: number, providerId: string) => {
    setSettings((prev) => ({
      ...prev,
      fallback_chain: prev.fallback_chain.map((entry, i) =>
        i === index ? { ...entry, provider_id: providerId, model_id: '' } : entry
      ),
    }))
  }, [])

  // 修改指定条目的模型
  const handleEntryModelChange = useCallback((index: number, modelId: string) => {
    setSettings((prev) => ({
      ...prev,
      fallback_chain: prev.fallback_chain.map((entry, i) =>
        i === index ? { ...entry, model_id: modelId } : entry
      ),
    }))
  }, [])

  const handleTimeoutChange = useCallback((value: string) => {
    const num = Number.parseInt(value, 10)
    if (Number.isNaN(num)) return
    setSettings((prev) => ({
      ...prev,
      run_timeout_seconds: Math.max(60, Math.min(3600, num)),
    }))
  }, [])

  const handleSave = useCallback(async () => {
    // 过滤掉未选全的条目（provider_id 或 model_id 为空）
    const validChain = settings.fallback_chain.filter(
      (e) => e.provider_id && e.model_id
    ) as FallbackModelEntry[]

    setSaving(true)
    try {
      const updated = await llmApi.updateRuntimeSettings({
        fallback_chain: validChain,
        run_timeout_seconds: settings.run_timeout_seconds,
      })
      setSettings(updated)
      useToastStore.getState().addToast('info', `兜底配置已保存（${updated.fallback_chain.length} 个备用）`)
    } catch (error) {
      console.error('Failed to save runtime settings:', error)
      useToastStore.getState().addToast('error', '保存兜底配置失败')
    } finally {
      setSaving(false)
    }
  }, [settings])

  return (
    <div className="rounded-lg border border-edge bg-surface-primary p-6">
      <h3 className="mb-2 text-lg font-semibold text-content-primary">运行兜底</h3>
      <p className="mb-4 text-sm text-content-muted">
        主模型超过设定时间未完成时，按列表顺序逐个尝试备用模型；全部失败时输出"当前无可用模型"。最多 3 个备用。
      </p>

      {loading ? (
        <div className="rounded-lg bg-surface-tertiary px-4 py-4 text-sm text-content-muted">
          正在加载配置...
        </div>
      ) : providers.length === 0 ? (
        <div className="rounded-lg bg-surface-tertiary px-4 py-4 text-sm text-content-muted">
          先保存至少一个供应商，才能配置备用模型。
        </div>
      ) : (
        <>
          {/* 备用模型链列表 */}
          <div className="space-y-2">
            {settings.fallback_chain.length === 0 && (
              <div className="rounded-lg bg-surface-tertiary px-3 py-3 text-sm text-content-muted">
                暂无备用模型，点击下方"添加备用"创建。
              </div>
            )}
            {settings.fallback_chain.map((entry, index) => {
              const provider = providers.find((p) => p.id === entry.provider_id)
              const models = provider ? provider.models.filter((m) => m.enabled) : []
              return (
                <div
                  key={index}
                  className="flex items-center gap-2 rounded-lg border border-edge p-2"
                >
                  <span className="shrink-0 w-6 text-center text-sm text-content-muted">
                    {index + 1}
                  </span>
                  <select
                    value={entry.provider_id}
                    onChange={(e) => handleEntryProviderChange(index, e.target.value)}
                    className="flex-1 rounded-lg border border-edge bg-surface-primary text-content-secondary px-2 py-1.5 text-sm focus:border-accent focus:ring-1 focus:ring-accent outline-none"
                  >
                    <option value="">选择供应商</option>
                    {providers.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                  <select
                    value={entry.model_id}
                    onChange={(e) => handleEntryModelChange(index, e.target.value)}
                    disabled={!provider}
                    className="flex-1 rounded-lg border border-edge bg-surface-primary text-content-secondary px-2 py-1.5 text-sm focus:border-accent focus:ring-1 focus:ring-accent outline-none disabled:opacity-50"
                  >
                    <option value="">选择模型</option>
                    {models.map((m) => (
                      <option key={m.id} value={m.id}>{m.display_name}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => handleRemoveEntry(index)}
                    className="shrink-0 rounded-lg p-1.5 text-content-muted hover:bg-surface-tertiary hover:text-status-error"
                    title="删除此备用"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              )
            })}
          </div>

          <button
            type="button"
            onClick={handleAddEntry}
            disabled={settings.fallback_chain.length >= 3}
            className="mt-3 inline-flex items-center gap-1 rounded-lg border border-edge px-3 py-1.5 text-sm text-content-secondary hover:bg-surface-tertiary disabled:cursor-not-allowed disabled:opacity-50"
            title={settings.fallback_chain.length >= 3 ? '最多 3 个备用模型' : '添加备用'}
          >
            <Plus className="h-4 w-4" />
            添加备用
          </button>

          {/* 超时秒数 */}
          <div className="mt-6 max-w-sm">
            <label className="mb-1 block text-sm font-medium text-content-secondary">
              超时秒数（60-3600）
            </label>
            <input
              type="number"
              min={60}
              max={3600}
              value={settings.run_timeout_seconds}
              onChange={(e) => handleTimeoutChange(e.target.value)}
              className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
            />
            <p className="mt-1 text-xs text-content-muted">
              主模型超过此时长未完成则切换备用（默认 600 秒 = 10 分钟）
            </p>
          </div>

          <div className="mt-4">
            <button
              onClick={() => { void handleSave() }}
              disabled={saving}
              className={`rounded-lg px-4 py-2 ${
                saving
                  ? 'bg-surface-tertiary text-content-muted'
                  : 'bg-accent text-white hover:bg-accent-hover'
              }`}
            >
              {saving ? '保存中...' : '保存兜底配置'}
            </button>
            {settings.fallback_chain.some((e) => e.provider_id && e.model_id) ? (
              <span className="ml-3 text-sm text-status-success">
                兜底已启用（{settings.fallback_chain.filter((e) => e.provider_id && e.model_id).length} 个）
              </span>
            ) : (
              <span className="ml-3 text-sm text-content-muted">未启用兜底</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}
