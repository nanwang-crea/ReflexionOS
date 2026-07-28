import { useEffect, useState } from 'react'
import { monitoringApi } from '@/features/monitoring/api/monitoring.api'
import { useToastStore } from '@/shared/stores/toast.store'
import type { MonitoringAlertSettings } from '@/types/monitoring'

const DEFAULT_SETTINGS: MonitoringAlertSettings = {
  enable_in_app_notifications: true,
  poll_interval_seconds: 60,
  enable_webhook_notifications: false,
  webhook_url: '',
  webhook_min_severity: 'critical',
  webhook_cooldown_seconds: 300,
  retry_request_count_warn: 3,
  failed_request_count_warn: 2,
  incomplete_cost_request_count_warn: 1,
  tool_failed_call_count_warn: 2,
  approval_denied_count_warn: 1,
  approval_wait_p95_ms_warn: 30_000,
  projection_lag_count_warn: 1,
  fallback_backlog_count_warn: 1,
  memory_queue_depth_critical: 1,
}

const FIELDS: Array<{
  key: keyof MonitoringAlertSettings
  label: string
  description: string
  type?: 'number' | 'boolean'
}> = [
  {
    key: 'enable_in_app_notifications',
    label: '应用内告警提醒',
    description: '开启后，活跃告警会通过全局 toast 主动提醒。',
    type: 'boolean',
  },
  {
    key: 'poll_interval_seconds',
    label: '轮询间隔 (秒)',
    description: '监控告警轮询周期。建议不要低于 15 秒。',
  },
  {
    key: 'enable_webhook_notifications',
    label: 'Webhook 外部通知',
    description: '开启后，后端会把新触发的告警发送到配置的 Webhook 地址。',
    type: 'boolean',
  },
  {
    key: 'webhook_cooldown_seconds',
    label: 'Webhook 冷却时间 (秒)',
    description: '同一条活跃告警重复发送前的最小间隔。',
  },
  {
    key: 'retry_request_count_warn',
    label: 'LLM 重试请求阈值',
    description: '当前窗口内真实 Provider 重试请求次数达到该值后触发。',
  },
  {
    key: 'failed_request_count_warn',
    label: 'LLM 失败请求阈值',
    description: '失败或中断的请求次数达到该值后触发。',
  },
  {
    key: 'incomplete_cost_request_count_warn',
    label: '费用不完整请求阈值',
    description: '无法精确定价或 Usage 不完整的请求数达到该值后触发。',
  },
  {
    key: 'tool_failed_call_count_warn',
    label: '工具失败阈值',
    description: '失败工具调用数达到该值后触发。',
  },
  {
    key: 'approval_denied_count_warn',
    label: '审批拒绝阈值',
    description: '审批拒绝次数达到该值后触发。',
  },
  {
    key: 'approval_wait_p95_ms_warn',
    label: '审批等待 P95 阈值 (ms)',
    description: '工具审批等待 P95 超过该毫秒值后触发。',
  },
  {
    key: 'projection_lag_count_warn',
    label: '投影滞后阈值',
    description: 'projection lag 条数达到该值后触发。',
  },
  {
    key: 'fallback_backlog_count_warn',
    label: 'Fallback backlog 阈值',
    description: 'journal backlog 条数达到该值后触发。',
  },
  {
    key: 'memory_queue_depth_critical',
    label: '内存队列临界值',
    description: 'memory queue 深度达到该值后按 critical 展示。',
  },
]

export function MonitoringPanel() {
  const [settings, setSettings] = useState<MonitoringAlertSettings>(DEFAULT_SETTINGS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    monitoringApi.alerts()
      .then((response) => {
        setSettings(response.data.settings)
      })
      .catch((error) => {
        console.error('Failed to load monitoring alert settings:', error)
        useToastStore.getState().addToast('warning', '加载监控告警设置失败')
      })
      .finally(() => setLoading(false))
  }, [])

  async function save() {
    setSaving(true)
    try {
      const response = await monitoringApi.updateAlerts(settings)
      setSettings(response.data)
      useToastStore.getState().addToast('info', '监控告警阈值已保存')
    } catch (error) {
      console.error('Failed to save monitoring alert settings:', error)
      useToastStore.getState().addToast('warning', '保存监控告警设置失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-edge bg-surface-primary p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-content-primary">监控告警阈值</h3>
            <p className="mt-2 text-sm leading-6 text-content-muted">
              为运行观测页设置默认告警阈值。当前先用于异常高亮和筛选入口，后续可以扩展成通知规则。
            </p>
          </div>
          <button
            type="button"
            onClick={() => { void save() }}
            disabled={loading || saving}
            className="rounded-xl bg-content-primary px-4 py-2 text-sm font-medium text-surface-primary transition hover:bg-content-primary/90 disabled:opacity-50"
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <label className="rounded-2xl border border-edge bg-surface-tertiary p-4 md:col-span-2">
            <div className="text-sm font-medium text-content-primary">Webhook 地址</div>
            <div className="mt-2 text-sm leading-6 text-content-muted">
              接收监控告警的外部地址。当前发送内容为 JSON POST，请确保目标可接收标准 JSON 请求。
            </div>
            <input
              type="url"
              value={settings.webhook_url || ''}
              onChange={(event) => {
                const value = event.target.value
                setSettings((current) => ({
                  ...current,
                  webhook_url: value,
                }))
              }}
              placeholder="https://example.com/monitoring/webhook"
              className="mt-4 w-full rounded-xl border border-edge bg-surface-primary px-3 py-2 text-sm text-content-primary outline-none"
            />
            <div className="mt-4">
              <div className="text-sm font-medium text-content-primary">最小告警等级</div>
              <div className="mt-2 flex gap-2">
                {['warning', 'critical'].map((severity) => (
                  <button
                    key={severity}
                    type="button"
                    onClick={() => {
                      setSettings((current) => ({
                        ...current,
                        webhook_min_severity: severity,
                      }))
                    }}
                    className={`rounded-full border px-3 py-1.5 text-sm ${
                      settings.webhook_min_severity === severity
                        ? 'border-edge bg-surface-primary text-content-primary'
                        : 'border-edge bg-surface-tertiary text-content-secondary'
                    }`}
                  >
                    {severity}
                  </button>
                ))}
              </div>
            </div>
          </label>
          {FIELDS.map((field) => (
            <label
              key={field.key}
              className="rounded-2xl border border-edge bg-surface-tertiary p-4"
            >
              <div className="text-sm font-medium text-content-primary">{field.label}</div>
              <div className="mt-2 text-sm leading-6 text-content-muted">
                {field.description}
              </div>
              {field.type === 'boolean' ? (
                <button
                  type="button"
                  onClick={() => {
                    const currentValue = Boolean(settings[field.key])
                    setSettings((current) => ({
                      ...current,
                      [field.key]: !currentValue,
                    }))
                  }}
                  className={`mt-4 inline-flex rounded-full border px-3 py-2 text-sm ${
                    settings[field.key]
                      ? 'border-status-success-border bg-status-success-soft text-status-success'
                      : 'border-edge bg-surface-primary text-content-secondary'
                  }`}
                >
                  {settings[field.key] ? '已开启' : '已关闭'}
                </button>
              ) : (
                <input
                  type="number"
                  min={0}
                  value={Number(settings[field.key])}
                  onChange={(event) => {
                    const next = Number(event.target.value)
                    setSettings((current) => ({
                      ...current,
                      [field.key]: Number.isFinite(next) && next >= 0 ? next : 0,
                    }))
                  }}
                  className="mt-4 w-full rounded-xl border border-edge bg-surface-primary px-3 py-2 text-sm text-content-primary outline-none"
                />
              )}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
