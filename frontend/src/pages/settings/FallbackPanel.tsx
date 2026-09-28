/**
 * 文件功能：设置页"运行兜底"面板组件
 * 文件描述：配置主模型超时后切换的备用供应商/模型，以及主 run 的墙钟超时秒数。
 *           主模型超时后系统自动切换到备用模型继续完整循环；备用也失败才输出"当前无可用模型"。
 * 核心逻辑：独立面板，直接调 llmApi.getRuntimeSettings/updateRuntimeSettings 读写，
 *          不走 useSettingsPageController（那个是供应商 CRUD 用的）；用 useSettingsStore 拿 providers 列表。
 */
import { useCallback, useEffect, useState } from 'react'
import { llmApi } from '@/features/llm/api/llm.api'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import { useToastStore } from '@/shared/stores/toast.store'
import type { RuntimeSettings } from '@/types/llm'

const DEFAULT_SETTINGS: RuntimeSettings = {
  fallback_provider_id: null,
  fallback_model_id: null,
  run_timeout_seconds: 600,
}

/**
 * 函数名：FallbackPanel
 * 入参：无
 * 功能：渲染运行兜底设置面板，支持选择备用供应商/模型 + 超时秒数并保存
 * 运行逻辑：
 *   1. 从 useSettingsStore 取已启用供应商列表（用于下拉）
 *   2. 挂载时调 llmApi.getRuntimeSettings 加载当前兜底配置
 *   3. 供应商/模型下拉联动（选供应商后模型列表跟着变）
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

  // 备用供应商选中后，其下已启用的模型列表
  const fallbackProvider = providers.find((p) => p.id === settings.fallback_provider_id) || null
  const fallbackModels = fallbackProvider
    ? fallbackProvider.models.filter((m) => m.enabled)
    : []

  const handleProviderChange = useCallback((providerId: string) => {
    // 切供应商时清空模型选择
    setSettings((prev) => ({
      ...prev,
      fallback_provider_id: providerId || null,
      fallback_model_id: null,
    }))
  }, [])

  const handleModelChange = useCallback((modelId: string) => {
    setSettings((prev) => ({ ...prev, fallback_model_id: modelId || null }))
  }, [])

  const handleTimeoutChange = useCallback((value: string) => {
    const num = Number.parseInt(value, 10)
    if (Number.isNaN(num)) return
    // 限制 60-3600
    setSettings((prev) => ({
      ...prev,
      run_timeout_seconds: Math.max(60, Math.min(3600, num)),
    }))
  }, [])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const updated = await llmApi.updateRuntimeSettings(settings)
      setSettings(updated)
      useToastStore.getState().addToast('info', '兜底配置已保存')
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
        主模型超过设定时间未完成时，自动切换到备用模型继续执行；备用模型也失败时输出"当前无可用模型"。
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
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-content-secondary">
                备用供应商
              </label>
              <select
                value={settings.fallback_provider_id || ''}
                onChange={(e) => handleProviderChange(e.target.value)}
                className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none"
              >
                <option value="">不启用兜底</option>
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-content-secondary">
                备用模型
              </label>
              <select
                value={settings.fallback_model_id || ''}
                onChange={(e) => handleModelChange(e.target.value)}
                disabled={!fallbackProvider}
                className="w-full rounded-lg border border-edge bg-surface-primary text-content-secondary px-3 py-2 focus:border-accent focus:ring-1 focus:ring-accent outline-none disabled:opacity-50"
              >
                <option value="">选择模型</option>
                {fallbackModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="mt-4 max-w-sm">
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
            {settings.fallback_provider_id && settings.fallback_model_id ? (
              <span className="ml-3 text-sm text-status-success">兜底已启用</span>
            ) : (
              <span className="ml-3 text-sm text-content-muted">未启用兜底</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}
