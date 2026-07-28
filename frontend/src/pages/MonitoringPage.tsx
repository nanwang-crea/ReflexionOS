import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  Bot,
  CircleDollarSign,
  Gauge,
  Monitor,
  RefreshCw,
  ShieldAlert,
  Wrench,
  X,
} from 'lucide-react'
import { monitoringApi } from '@/features/monitoring/api/monitoring.api'
import {
  buildMonitoringSearchParams,
  parseMonitoringSearchState,
} from '@/features/monitoring/monitoringSearchParams'
import { projectApi } from '@/features/projects/api/project.api'
import { useToastStore } from '@/shared/stores/toast.store'
import type {
  MonitoringAnomalyResponse,
  MonitoringAlertStatusResponse,
  MonitoringOverviewResponse,
  MonitoringProviderRequestDetail,
  MonitoringProviderRequestItem,
  MonitoringToolCallDetail,
  MonitoringToolCallItem,
  MonitoringTrendPoint,
} from '@/types/monitoring'
import type { Project } from '@/types/project'

const WINDOW_OPTIONS = [
  { label: '1 小时', value: 1 },
  { label: '24 小时', value: 24 },
  { label: '7 天', value: 24 * 7 },
] as const

function formatNanoUsd(value?: number | null) {
  if (value == null) {
    return '--'
  }
  return `$${(value / 1_000_000_000).toFixed(value < 100_000_000 ? 4 : 2)}`
}

function formatCount(value?: number | null) {
  if (value == null) {
    return '--'
  }
  return new Intl.NumberFormat('zh-CN').format(value)
}

function formatDurationMs(value?: number | null) {
  if (value == null) {
    return '--'
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}s`
  }
  return `${value}ms`
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '--'
  }
  return new Date(value).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function statusBadgeClass(status: string) {
  if (status === 'healthy' || status === 'completed' || status === 'exact') {
    return 'bg-status-success-soft text-status-success border-status-success-border'
  }
  if (
    status === 'degraded'
    || status === 'estimated'
    || status === 'incomplete'
    || status === 'waiting_for_approval'
    || status === 'requested'
  ) {
    return 'bg-status-warning-soft text-status-warning border-status-warning-border'
  }
  return 'bg-status-error-soft text-status-error border-status-error-border'
}

function MetricCard({
  title,
  value,
  hint,
  icon: Icon,
}: {
  title: string
  value: string
  hint: string
  icon: typeof Bot
}) {
  return (
    <div className="rounded-2xl border border-edge bg-surface-tertiary p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm text-content-muted">{title}</div>
          <div className="mt-2 text-2xl font-semibold text-content-primary">{value}</div>
        </div>
        <div className="rounded-xl bg-surface-primary p-2 text-content-muted">
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-3 text-sm text-content-muted">{hint}</div>
    </div>
  )
}

function TrendCard({
  title,
  value,
  hint,
  points,
  color,
}: {
  title: string
  value: string
  hint: string
  points: number[]
  color: string
}) {
  const width = 320
  const height = 88
  const max = Math.max(...points, 0)
  const normalized = points.length
    ? points.map((point, index) => {
        const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width
        const y = max === 0 ? height - 8 : height - 8 - (point / max) * (height - 18)
        return `${x},${y}`
      })
    : []

  return (
    <div className="rounded-2xl border border-edge bg-surface-tertiary p-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-sm text-content-muted">{title}</div>
          <div className="mt-2 text-2xl font-semibold text-content-primary">{value}</div>
        </div>
        <div className="text-right text-sm text-content-muted">{hint}</div>
      </div>
      <div className="mt-4 overflow-hidden rounded-xl border border-edge bg-surface-primary px-3 py-2">
        {points.length ? (
          <svg viewBox={`0 0 ${width} ${height}`} className="h-24 w-full">
            <polyline
              fill="none"
              stroke={color}
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              points={normalized.join(' ')}
            />
          </svg>
        ) : (
          <div className="flex h-24 items-center justify-center text-sm text-content-muted">
            当前窗口没有趋势数据。
          </div>
        )}
      </div>
    </div>
  )
}

function KeyValueRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-edge py-2 last:border-b-0">
      <div className="text-sm text-content-muted">{label}</div>
      <div className="max-w-[60%] text-right text-sm text-content-primary">{value}</div>
    </div>
  )
}

function DetailPanel({
  title,
  subtitle,
  children,
  onClose,
}: {
  title: string
  subtitle: string
  children: ReactNode
  onClose: () => void
}) {
  return (
    <aside className="rounded-2xl border border-edge bg-surface-tertiary p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-content-primary">{title}</div>
          <div className="mt-1 text-sm text-content-muted">{subtitle}</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl border border-edge bg-surface-primary p-2 text-content-muted transition hover:text-content-primary"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-4 space-y-4">{children}</div>
    </aside>
  )
}

function FilterChip({
  label,
  onClear,
}: {
  label: string
  onClear: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClear}
      className="inline-flex items-center gap-2 rounded-full border border-edge bg-surface-primary px-3 py-1.5 text-xs text-content-secondary transition hover:text-content-primary"
    >
      <span>{label}</span>
      <X className="h-3.5 w-3.5" />
    </button>
  )
}

function trendValues(points: MonitoringTrendPoint[], key: keyof MonitoringTrendPoint) {
  return points.map((point) => {
    const value = point[key]
    return typeof value === 'number' ? value : 0
  })
}

export default function MonitoringPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const searchState = parseMonitoringSearchState(searchParams)
  const [projects, setProjects] = useState<Project[]>([])
  const [overview, setOverview] = useState<MonitoringOverviewResponse | null>(null)
  const [anomalies, setAnomalies] = useState<MonitoringAnomalyResponse | null>(null)
  const [alertStatus, setAlertStatus] = useState<MonitoringAlertStatusResponse | null>(null)
  const [providerRequests, setProviderRequests] = useState<MonitoringProviderRequestItem[]>([])
  const [toolCalls, setToolCalls] = useState<MonitoringToolCallItem[]>([])
  const [trendPoints, setTrendPoints] = useState<MonitoringTrendPoint[]>([])
  const [selectedRequest, setSelectedRequest] = useState<MonitoringProviderRequestDetail | null>(null)
  const [selectedTool, setSelectedTool] = useState<MonitoringToolCallDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    projectApi.list()
      .then((response) => setProjects(response.data))
      .catch((error) => {
        console.error('Failed to load projects for monitoring:', error)
        useToastStore.getState().addToast('warning', '加载项目列表失败')
      })
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      if (cancelled) {
        return
      }
      setLoading(true)
      try {
        const params = {
          project_id: searchState.projectId === 'all' ? undefined : searchState.projectId,
          window_hours: searchState.windowHours,
          limit: 20,
          bucket_hours: searchState.windowHours <= 24 ? 1 : 6,
        }
        const [
          overviewResponse,
          anomaliesResponse,
          alertsResponse,
          requestsResponse,
          toolsResponse,
          trendsResponse,
        ] = await Promise.all([
          monitoringApi.overview(params),
          monitoringApi.anomalies(params),
          monitoringApi.alerts(params),
          monitoringApi.listProviderRequests({
            ...params,
            status: searchState.requestStatusFilter === 'all' ? undefined : searchState.requestStatusFilter,
            cost_status: searchState.requestCostStatusFilter === 'all' ? undefined : searchState.requestCostStatusFilter,
          }),
          monitoringApi.listToolCalls({
            ...params,
            status: searchState.toolStatusFilter === 'all' ? undefined : searchState.toolStatusFilter,
            terminal_reason: searchState.toolTerminalReasonFilter === 'all' ? undefined : searchState.toolTerminalReasonFilter,
          }),
          monitoringApi.trends(params),
        ])
        if (cancelled) {
          return
        }
        setOverview(overviewResponse.data)
        setAnomalies(anomaliesResponse.data)
        setAlertStatus(alertsResponse.data)
        setProviderRequests(requestsResponse.data.items)
        setToolCalls(toolsResponse.data.items)
        setTrendPoints(trendsResponse.data.points)
      } catch (error) {
        console.error('Failed to load monitoring data:', error)
        useToastStore.getState().addToast('warning', '加载监控数据失败')
      } finally {
        if (!cancelled) {
          setLoading(false)
          setRefreshing(false)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [
    searchState.projectId,
    searchState.windowHours,
    refreshing,
    searchState.requestStatusFilter,
    searchState.requestCostStatusFilter,
    searchState.toolStatusFilter,
    searchState.toolTerminalReasonFilter,
  ])

  const selectedProject = searchState.projectId === 'all'
    ? '全部项目'
    : projects.find((project) => project.id === searchState.projectId)?.name || '当前项目'

  const llmCostTrend = trendValues(trendPoints, 'llm_total_cost_nano_usd')
  const llmFailureTrend = trendValues(trendPoints, 'llm_failed_count')
  const toolFailureTrend = trendValues(trendPoints, 'tool_failed_count')
  const toolDeniedTrend = trendValues(trendPoints, 'tool_denied_count')
  const hasActiveRequestFilters = searchState.requestStatusFilter !== 'all' || searchState.requestCostStatusFilter !== 'all'
  const hasActiveToolFilters = searchState.toolStatusFilter !== 'all' || searchState.toolTerminalReasonFilter !== 'all'

  function updateSearchState(
    patch: Partial<typeof searchState>,
    { replace = false }: { replace?: boolean } = {},
  ) {
    const nextState = {
      ...searchState,
      ...patch,
    }
    setSearchParams(buildMonitoringSearchParams(nextState), { replace })
  }

  async function openRequestDetail(requestId: string) {
    try {
      const response = await monitoringApi.getProviderRequestDetail(requestId)
      setSelectedTool(null)
      setSelectedRequest(response.data)
      updateSearchState(
        {
          selectedRequestId: requestId,
          selectedToolId: null,
        },
      )
    } catch (error) {
      console.error('Failed to load provider request detail:', error)
      useToastStore.getState().addToast('warning', '加载 Provider 请求详情失败')
    }
  }

  async function openToolDetail(toolCallMetricId: string) {
    try {
      const response = await monitoringApi.getToolCallDetail(toolCallMetricId)
      setSelectedRequest(null)
      setSelectedTool(response.data)
      updateSearchState(
        {
          selectedToolId: toolCallMetricId,
          selectedRequestId: null,
        },
      )
    } catch (error) {
      console.error('Failed to load tool call detail:', error)
      useToastStore.getState().addToast('warning', '加载工具调用详情失败')
    }
  }

  useEffect(() => {
    let cancelled = false
    if (!searchState.selectedRequestId) {
      setSelectedRequest(null)
      return () => {
        cancelled = true
      }
    }
    if (selectedRequest?.id === searchState.selectedRequestId) {
      return () => {
        cancelled = true
      }
    }

    monitoringApi.getProviderRequestDetail(searchState.selectedRequestId)
      .then((response) => {
        if (!cancelled) {
          setSelectedRequest(response.data)
        }
      })
      .catch((error) => {
        console.error('Failed to restore provider request detail from URL:', error)
        if (!cancelled) {
          setSelectedRequest(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [searchState.selectedRequestId, selectedRequest?.id])

  useEffect(() => {
    let cancelled = false
    if (!searchState.selectedToolId) {
      setSelectedTool(null)
      return () => {
        cancelled = true
      }
    }
    if (selectedTool?.id === searchState.selectedToolId) {
      return () => {
        cancelled = true
      }
    }

    monitoringApi.getToolCallDetail(searchState.selectedToolId)
      .then((response) => {
        if (!cancelled) {
          setSelectedTool(response.data)
        }
      })
      .catch((error) => {
        console.error('Failed to restore tool call detail from URL:', error)
        if (!cancelled) {
          setSelectedTool(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [searchState.selectedToolId, selectedTool?.id])

  function focusIncompleteRequests() {
    updateSearchState({
      requestStatusFilter: 'all',
      requestCostStatusFilter: 'incomplete',
      selectedRequestId: null,
    })
  }

  function focusUnpricedRequests() {
    updateSearchState({
      requestStatusFilter: 'all',
      requestCostStatusFilter: 'unpriced',
      selectedRequestId: null,
    })
  }

  function focusFailedRequests() {
    updateSearchState({
      requestStatusFilter: 'failed',
      selectedRequestId: null,
    })
  }

  function focusDeniedTools() {
    updateSearchState({
      toolStatusFilter: 'failed',
      toolTerminalReasonFilter: 'denied',
      selectedToolId: null,
    })
  }

  function focusWaitingTools() {
    updateSearchState({
      toolStatusFilter: 'waiting_for_approval',
      toolTerminalReasonFilter: 'all',
      selectedToolId: null,
    })
  }

  function clearRequestFilters() {
    updateSearchState({
      requestStatusFilter: 'all',
      requestCostStatusFilter: 'all',
      selectedRequestId: null,
    })
  }

  function clearToolFilters() {
    updateSearchState({
      toolStatusFilter: 'all',
      toolTerminalReasonFilter: 'all',
      selectedToolId: null,
    })
  }

  function applyAlertAction(key: string) {
    if (
      key === 'retry_request_count_warn'
      || key === 'failed_request_count_warn'
    ) {
      focusFailedRequests()
      return
    }
    if (
      key === 'incomplete_cost_request_count_warn'
    ) {
      focusIncompleteRequests()
      return
    }
    if (key === 'tool_failed_call_count_warn') {
      updateSearchState({
        toolStatusFilter: 'failed',
        selectedToolId: null,
      })
      return
    }
    if (key === 'approval_denied_count_warn') {
      focusDeniedTools()
      return
    }
    if (key === 'approval_wait_p95_ms_warn') {
      focusWaitingTools()
      return
    }
    navigate('/settings')
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-primary">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
        <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-surface-tertiary px-3 py-1 text-sm text-content-muted">
              <Monitor className="h-4 w-4" />
              <span>监控中心</span>
            </div>
            <h1 className="text-2xl font-semibold text-content-primary sm:text-3xl">运行观测</h1>
            <p className="mt-3 max-w-3xl text-[16px] leading-7 text-content-muted">
              查看 LLM 请求、真实重试、费用快照、工具失败和审批等待，先核对采集准确性，再看趋势。
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <select
              value={searchState.projectId}
              onChange={(event) => updateSearchState({
                projectId: event.target.value,
                selectedRequestId: null,
                selectedToolId: null,
              })}
              className="rounded-xl border border-edge bg-surface-tertiary px-3 py-2 text-sm text-content-primary outline-none"
            >
              <option value="all">全部项目</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>{project.name}</option>
              ))}
            </select>
            <div className="flex rounded-xl border border-edge bg-surface-tertiary p-1">
              {WINDOW_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => updateSearchState({
                    windowHours: option.value,
                    selectedRequestId: null,
                    selectedToolId: null,
                  })}
                  className={`rounded-lg px-3 py-1.5 text-sm transition ${
                    searchState.windowHours === option.value
                      ? 'bg-surface-primary text-content-primary shadow-sm'
                      : 'text-content-secondary hover:text-content-primary'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setRefreshing(true)}
              disabled={loading}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-edge bg-surface-tertiary px-3 py-2 text-sm text-content-secondary transition hover:bg-surface-secondary disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>
        </div>

        <div className="mb-6 rounded-2xl border border-edge bg-surface-tertiary p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-sm text-content-muted">观测范围</div>
              <div className="mt-1 text-lg font-medium text-content-primary">{selectedProject}</div>
            </div>
            <div className="flex flex-wrap gap-3 text-sm text-content-muted">
              <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${statusBadgeClass(overview?.health.status || 'degraded')}`}>
                <Gauge className="h-4 w-4" />
                {overview?.health.status || (loading ? 'loading' : 'degraded')}
              </span>
              <span>最后事件: {formatDateTime(overview?.health.last_event_recorded_at)}</span>
              <span>最后投影: {formatDateTime(overview?.health.last_projection_at)}</span>
            </div>
          </div>
          {overview && overview.health.status !== 'healthy' && (
            <div className="mt-4 flex items-start gap-3 rounded-xl border border-status-warning-border bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                数据可能不完整。projection lag {overview.health.projection_lag_count}，fallback backlog {overview.health.fallback_backlog_count}，内存队列 {overview.health.memory_queue_depth}，已丢弃 {overview.health.dropped_metrics_count}。
              </div>
            </div>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            title="LLM 费用"
            value={overview ? formatNanoUsd(overview.llm.total_cost_nano_usd) : '--'}
            hint={`Provider 请求 ${overview ? formatCount(overview.llm.provider_request_count) : '--'} 次`}
            icon={CircleDollarSign}
          />
          <MetricCard
            title="重试请求"
            value={overview ? formatCount(overview.llm.retry_request_count) : '--'}
            hint={`失败 ${overview ? formatCount(overview.llm.failed_request_count) : '--'} 次`}
            icon={Bot}
          />
          <MetricCard
            title="工具调用"
            value={overview ? formatCount(overview.tools.tool_call_count) : '--'}
            hint={`失败 ${overview ? formatCount(overview.tools.failed_call_count) : '--'} 次`}
            icon={Wrench}
          />
          <MetricCard
            title="审批拒绝"
            value={overview ? formatCount(overview.tools.approval_denied_count) : '--'}
            hint={`等待审批 ${overview ? formatCount(overview.tools.waiting_for_approval_count) : '--'} 次`}
            icon={ShieldAlert}
          />
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={focusFailedRequests}
            className="rounded-full border border-status-error-border bg-status-error-soft px-3 py-1.5 text-xs text-status-error transition hover:opacity-80"
          >
            只看失败请求
          </button>
          <button
            type="button"
            onClick={focusUnpricedRequests}
            className="rounded-full border border-status-warning-border bg-status-warning-soft px-3 py-1.5 text-xs text-status-warning transition hover:opacity-80"
          >
            只看未定价请求
          </button>
          <button
            type="button"
            onClick={focusDeniedTools}
            className="rounded-full border border-status-error-border bg-status-error-soft px-3 py-1.5 text-xs text-status-error transition hover:opacity-80"
          >
            只看被拒绝工具
          </button>
          <button
            type="button"
            onClick={focusWaitingTools}
            className="rounded-full border border-status-warning-border bg-status-warning-soft px-3 py-1.5 text-xs text-status-warning transition hover:opacity-80"
          >
            只看等待审批
          </button>
          {hasActiveRequestFilters ? (
            <FilterChip
              label={`请求筛选: ${searchState.requestStatusFilter}/${searchState.requestCostStatusFilter}`}
              onClear={clearRequestFilters}
            />
          ) : null}
          {hasActiveToolFilters ? (
            <FilterChip
              label={`工具筛选: ${searchState.toolStatusFilter}/${searchState.toolTerminalReasonFilter}`}
              onClear={clearToolFilters}
            />
          ) : null}
        </div>

        <div className="mt-8 rounded-2xl border border-edge bg-surface-tertiary p-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-content-primary">已触发告警</h2>
              <p className="mt-1 text-sm text-content-muted">
                当前根据配置阈值计算的活跃告警。可以直接跳到对应问题集，或去设置里调整阈值。
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate('/settings')}
              className="rounded-xl border border-edge bg-surface-primary px-3 py-2 text-sm text-content-secondary transition hover:text-content-primary"
            >
              调整阈值
            </button>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {alertStatus?.active_alerts.length ? alertStatus.active_alerts.map((alert) => (
              <div
                key={alert.key}
                className={`rounded-2xl border px-4 py-4 ${
                  alert.severity === 'critical'
                    ? 'border-status-error-border bg-status-error-soft'
                    : 'border-status-warning-border bg-status-warning-soft'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-content-primary">{alert.title}</div>
                    <div className="mt-2 text-sm text-content-secondary">{alert.description}</div>
                  </div>
                  <span className={`inline-flex rounded-full border px-2 py-1 text-xs ${statusBadgeClass(alert.severity)}`}>
                    {alert.severity}
                  </span>
                </div>
                <div className="mt-4 text-sm text-content-muted">
                  当前 {formatCount(alert.current_value)} / 阈值 {formatCount(alert.threshold_value)}
                </div>
                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    onClick={() => applyAlertAction(alert.key)}
                    className="rounded-full border border-edge bg-surface-primary px-3 py-1.5 text-xs text-content-secondary transition hover:text-content-primary"
                  >
                    查看问题集
                  </button>
                </div>
              </div>
            )) : (
              <div className="rounded-xl bg-surface-primary px-4 py-6 text-sm text-content-muted">
                当前没有达到告警阈值的指标。
              </div>
            )}
          </div>
        </div>

        <div className="mt-8 grid gap-6 xl:grid-cols-2">
          <TrendCard
            title="LLM 费用走势"
            value={overview ? formatNanoUsd(overview.llm.total_cost_nano_usd) : '--'}
            hint="按时间桶累计真实 request 成本"
            points={llmCostTrend}
            color="#0f766e"
          />
          <TrendCard
            title="失败走势"
            value={overview ? formatCount(overview.llm.failed_request_count + overview.tools.failed_call_count) : '--'}
            hint="LLM 失败 + 工具失败"
            points={llmFailureTrend.map((value, index) => value + (toolFailureTrend[index] || 0))}
            color="#dc2626"
          />
        </div>

        <div className="mt-8 grid gap-6 xl:grid-cols-2">
          <section className="rounded-2xl border border-edge bg-surface-tertiary p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-content-primary">异常模型</h2>
                <p className="mt-1 text-sm text-content-muted">重试、失败和费用不完整最集中的模型。</p>
              </div>
              <div className="text-sm text-content-muted">
                费用不完整 {formatCount(anomalies?.incomplete_cost_request_count)}
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {anomalies?.hottest_retry_models.length ? anomalies.hottest_retry_models.map((item) => (
                <div key={`${item.provider_id}:${item.model_id}`} className="rounded-xl bg-surface-primary px-4 py-3">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium text-content-primary">{item.model_id}</div>
                      <div className="mt-1 text-xs text-content-muted">{item.provider_id}</div>
                    </div>
                    <div className="text-right text-sm text-content-secondary">
                      <div>重试 {formatCount(item.retry_request_count)}</div>
                      <div className="mt-1 text-xs text-content-muted">
                        失败 {formatCount(item.failed_request_count)} / 不完整 {formatCount(item.incomplete_cost_count)}
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.retry_request_count > 0 ? (
                      <button
                        type="button"
                        onClick={focusFailedRequests}
                        className="rounded-full border border-edge px-2.5 py-1 text-xs text-content-secondary transition hover:text-content-primary"
                      >
                        查看失败请求
                      </button>
                    ) : null}
                    {item.incomplete_cost_count > 0 ? (
                      <button
                        type="button"
                        onClick={focusIncompleteRequests}
                        className="rounded-full border border-edge px-2.5 py-1 text-xs text-content-secondary transition hover:text-content-primary"
                      >
                        查看不完整费用
                      </button>
                    ) : null}
                  </div>
                </div>
              )) : (
                <div className="rounded-xl bg-surface-primary px-4 py-6 text-sm text-content-muted">当前窗口没有明显异常模型。</div>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-edge bg-surface-tertiary p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-content-primary">异常工具</h2>
                <p className="mt-1 text-sm text-content-muted">失败、拒绝或长期等待审批最集中的工具。</p>
              </div>
              <div className="text-sm text-content-muted">
                等待审批 {formatCount(anomalies?.waiting_approval_call_count)}
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {anomalies?.noisiest_tools.length ? anomalies.noisiest_tools.map((item) => (
                <div key={item.tool_name} className="rounded-xl bg-surface-primary px-4 py-3">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-sm font-medium text-content-primary">{item.tool_name}</div>
                      <div className="mt-1 text-xs text-content-muted">
                        平均审批等待 {formatDurationMs(item.average_approval_wait_ms)}
                      </div>
                    </div>
                    <div className="text-right text-sm text-content-secondary">
                      <div>失败 {formatCount(item.failed_call_count)}</div>
                      <div className="mt-1 text-xs text-content-muted">
                        拒绝 {formatCount(item.denied_call_count)} / 等待 {formatCount(item.waiting_for_approval_count)}
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.denied_call_count > 0 ? (
                      <button
                        type="button"
                        onClick={focusDeniedTools}
                        className="rounded-full border border-edge px-2.5 py-1 text-xs text-content-secondary transition hover:text-content-primary"
                      >
                        查看被拒绝工具
                      </button>
                    ) : null}
                    {item.waiting_for_approval_count > 0 ? (
                      <button
                        type="button"
                        onClick={focusWaitingTools}
                        className="rounded-full border border-edge px-2.5 py-1 text-xs text-content-secondary transition hover:text-content-primary"
                      >
                        查看等待审批
                      </button>
                    ) : null}
                  </div>
                </div>
              )) : (
                <div className="rounded-xl bg-surface-primary px-4 py-6 text-sm text-content-muted">当前窗口没有明显异常工具。</div>
              )}
            </div>
          </section>
        </div>

        <div className="mt-8 grid gap-6 xl:grid-cols-2">
          <section className="rounded-2xl border border-edge bg-surface-tertiary p-4">
            <h2 className="text-lg font-semibold text-content-primary">高频模型</h2>
            <div className="mt-4 space-y-3">
              {overview?.top_models.length ? overview.top_models.map((item) => (
                <div key={`${item.provider_id}:${item.model_id}`} className="flex items-center justify-between gap-4 rounded-xl bg-surface-primary px-4 py-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-content-primary">{item.model_id}</div>
                    <div className="mt-1 text-xs text-content-muted">{item.provider_id}</div>
                  </div>
                  <div className="text-right text-sm text-content-secondary">
                    <div>{formatCount(item.request_count)} 次</div>
                    <div className="mt-1 text-xs text-content-muted">重试 {formatCount(item.retry_request_count)} / {formatNanoUsd(item.total_cost_nano_usd)}</div>
                  </div>
                </div>
              )) : (
                <div className="rounded-xl bg-surface-primary px-4 py-6 text-sm text-content-muted">当前窗口没有模型请求。</div>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-edge bg-surface-tertiary p-4">
            <h2 className="text-lg font-semibold text-content-primary">高风险工具</h2>
            <div className="mt-4 space-y-3">
              {overview?.top_tools.length ? overview.top_tools.map((item) => (
                <div key={item.tool_name} className="flex items-center justify-between gap-4 rounded-xl bg-surface-primary px-4 py-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-content-primary">{item.tool_name}</div>
                    <div className="mt-1 text-xs text-content-muted">
                      失败 {formatCount(item.failed_call_count)} / 拒绝 {formatCount(item.denied_call_count)}
                    </div>
                  </div>
                  <div className="text-right text-sm text-content-secondary">
                    <div>{formatCount(item.call_count)} 次</div>
                    <div className="mt-1 text-xs text-content-muted">平均耗时 {formatDurationMs(item.average_total_duration_ms)}</div>
                  </div>
                </div>
              )) : (
                <div className="rounded-xl bg-surface-primary px-4 py-6 text-sm text-content-muted">当前窗口没有工具调用。</div>
              )}
            </div>
          </section>
        </div>

        <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
          <section className="rounded-2xl border border-edge bg-surface-tertiary p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-content-primary">最近 Provider 请求</h2>
                <p className="mt-1 text-sm text-content-muted">点击一行查看 pricing、usage 和错误详情。</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <select
                  value={searchState.requestStatusFilter}
                  onChange={(event) => updateSearchState({
                    requestStatusFilter: event.target.value,
                    selectedRequestId: null,
                  })}
                  className="rounded-lg border border-edge bg-surface-primary px-2 py-1.5 text-xs text-content-primary outline-none"
                >
                  <option value="all">全部状态</option>
                  <option value="completed">completed</option>
                  <option value="failed">failed</option>
                  <option value="interrupted">interrupted</option>
                </select>
                <select
                  value={searchState.requestCostStatusFilter}
                  onChange={(event) => updateSearchState({
                    requestCostStatusFilter: event.target.value,
                    selectedRequestId: null,
                  })}
                  className="rounded-lg border border-edge bg-surface-primary px-2 py-1.5 text-xs text-content-primary outline-none"
                >
                  <option value="all">全部费用状态</option>
                  <option value="exact">exact</option>
                  <option value="estimated">estimated</option>
                  <option value="incomplete">incomplete</option>
                  <option value="unpriced">unpriced</option>
                </select>
              </div>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-content-muted">
                  <tr className="border-b border-edge">
                    <th className="px-3 py-2 font-medium">时间</th>
                    <th className="px-3 py-2 font-medium">模型</th>
                    <th className="px-3 py-2 font-medium">状态</th>
                    <th className="px-3 py-2 font-medium">attempt</th>
                    <th className="px-3 py-2 font-medium">输入/输出</th>
                    <th className="px-3 py-2 font-medium">费用</th>
                    <th className="px-3 py-2 font-medium">耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {providerRequests.length ? providerRequests.map((item) => (
                    <tr
                      key={item.id}
                      className="cursor-pointer border-b border-edge transition hover:bg-surface-primary last:border-b-0"
                      onClick={() => openRequestDetail(item.id)}
                    >
                      <td className="px-3 py-3 text-content-secondary">{formatDateTime(item.started_at)}</td>
                      <td className="px-3 py-3">
                        <div className="text-content-primary">{item.model_id || '--'}</div>
                        <div className="mt-1 text-xs text-content-muted">{item.provider_id || '--'}</div>
                      </td>
                      <td className="px-3 py-3">
                        <span className={`inline-flex rounded-full border px-2 py-1 text-xs ${statusBadgeClass(item.status)}`}>
                          {item.status}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-content-secondary">{item.request_attempt_index}</td>
                      <td className="px-3 py-3 text-content-secondary">
                        {formatCount(item.input_tokens)} / {formatCount(item.output_tokens)}
                      </td>
                      <td className="px-3 py-3">
                        <div className="text-content-primary">{formatNanoUsd(item.total_cost_nano_usd)}</div>
                        <div className="mt-1 text-xs text-content-muted">{item.cost_status}</div>
                      </td>
                      <td className="px-3 py-3 text-content-secondary">{formatDurationMs(item.duration_ms)}</td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={7} className="px-3 py-8 text-center text-content-muted">当前窗口没有 Provider 请求。</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {selectedRequest ? (
            <DetailPanel
              title="Provider 请求详情"
              subtitle={`${selectedRequest.provider_id || '--'} / ${selectedRequest.model_id || '--'}`}
              onClose={() => updateSearchState({ selectedRequestId: null })}
            >
              <div className="rounded-xl bg-surface-primary p-4">
                <KeyValueRow label="请求 ID" value={selectedRequest.id} />
                <KeyValueRow label="logical_call_id" value={selectedRequest.logical_call_id} />
                <KeyValueRow label="状态" value={selectedRequest.status} />
                <KeyValueRow label="finish_reason" value={selectedRequest.finish_reason || '--'} />
                <KeyValueRow label="开始时间" value={formatDateTime(selectedRequest.started_at)} />
                <KeyValueRow label="耗时" value={formatDurationMs(selectedRequest.duration_ms)} />
                <KeyValueRow label="cost_status" value={selectedRequest.cost_status} />
                <KeyValueRow label="pricing" value={selectedRequest.pricing_match_rule || '--'} />
                <KeyValueRow label="输入费用" value={formatNanoUsd(selectedRequest.input_cost_nano_usd)} />
                <KeyValueRow label="输出费用" value={formatNanoUsd(selectedRequest.output_cost_nano_usd)} />
                <KeyValueRow label="缓存费用" value={formatNanoUsd(selectedRequest.cached_input_cost_nano_usd)} />
                <KeyValueRow label="总费用" value={formatNanoUsd(selectedRequest.total_cost_nano_usd)} />
                <KeyValueRow label="错误" value={selectedRequest.error_message || '--'} />
              </div>
            </DetailPanel>
          ) : null}
        </div>

        <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
          <section className="rounded-2xl border border-edge bg-surface-tertiary p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-content-primary">最近工具调用</h2>
                <p className="mt-1 text-sm text-content-muted">点击一行查看审批历史、等待耗时和终态原因。</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <select
                  value={searchState.toolStatusFilter}
                  onChange={(event) => updateSearchState({
                    toolStatusFilter: event.target.value,
                    selectedToolId: null,
                  })}
                  className="rounded-lg border border-edge bg-surface-primary px-2 py-1.5 text-xs text-content-primary outline-none"
                >
                  <option value="all">全部状态</option>
                  <option value="completed">completed</option>
                  <option value="failed">failed</option>
                  <option value="waiting_for_approval">waiting_for_approval</option>
                  <option value="interrupted">interrupted</option>
                </select>
                <select
                  value={searchState.toolTerminalReasonFilter}
                  onChange={(event) => updateSearchState({
                    toolTerminalReasonFilter: event.target.value,
                    selectedToolId: null,
                  })}
                  className="rounded-lg border border-edge bg-surface-primary px-2 py-1.5 text-xs text-content-primary outline-none"
                >
                  <option value="all">全部终态原因</option>
                  <option value="denied">denied</option>
                  <option value="failed">failed</option>
                  <option value="completed">completed</option>
                  <option value="recovered_after_restart">recovered_after_restart</option>
                </select>
              </div>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-content-muted">
                  <tr className="border-b border-edge">
                    <th className="px-3 py-2 font-medium">时间</th>
                    <th className="px-3 py-2 font-medium">工具</th>
                    <th className="px-3 py-2 font-medium">状态</th>
                    <th className="px-3 py-2 font-medium">审批</th>
                    <th className="px-3 py-2 font-medium">等待</th>
                    <th className="px-3 py-2 font-medium">总耗时</th>
                    <th className="px-3 py-2 font-medium">原因</th>
                  </tr>
                </thead>
                <tbody>
                  {toolCalls.length ? toolCalls.map((item) => (
                    <tr
                      key={item.id}
                      className="cursor-pointer border-b border-edge transition hover:bg-surface-primary last:border-b-0"
                      onClick={() => openToolDetail(item.id)}
                    >
                      <td className="px-3 py-3 text-content-secondary">{formatDateTime(item.started_at)}</td>
                      <td className="px-3 py-3">
                        <div className="text-content-primary">{item.tool_name}</div>
                        <div className="mt-1 text-xs text-content-muted">{item.tool_call_id}</div>
                      </td>
                      <td className="px-3 py-3">
                        <span className={`inline-flex rounded-full border px-2 py-1 text-xs ${statusBadgeClass(item.status)}`}>
                          {item.status}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-content-secondary">
                        {item.latest_approval_event_type || '--'}
                      </td>
                      <td className="px-3 py-3 text-content-secondary">{formatDurationMs(item.approval_wait_ms)}</td>
                      <td className="px-3 py-3 text-content-secondary">{formatDurationMs(item.total_duration_ms)}</td>
                      <td className="px-3 py-3">
                        <div className="text-content-primary">{item.terminal_reason || item.error_category || '--'}</div>
                        <div className="mt-1 max-w-[320px] truncate text-xs text-content-muted">
                          {item.error_message || item.latest_approval_reason || '--'}
                        </div>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={7} className="px-3 py-8 text-center text-content-muted">当前窗口没有工具调用。</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {selectedTool ? (
            <DetailPanel
              title="工具调用详情"
              subtitle={`${selectedTool.tool_name} / ${selectedTool.tool_call_id}`}
              onClose={() => updateSearchState({ selectedToolId: null })}
            >
              <div className="rounded-xl bg-surface-primary p-4">
                <KeyValueRow label="metric_id" value={selectedTool.id} />
                <KeyValueRow label="invocation_id" value={selectedTool.invocation_id} />
                <KeyValueRow label="状态" value={selectedTool.status} />
                <KeyValueRow label="终态原因" value={selectedTool.terminal_reason || '--'} />
                <KeyValueRow label="开始时间" value={formatDateTime(selectedTool.started_at)} />
                <KeyValueRow label="等待审批" value={formatDurationMs(selectedTool.approval_wait_ms)} />
                <KeyValueRow label="执行耗时" value={formatDurationMs(selectedTool.execution_duration_ms)} />
                <KeyValueRow label="总耗时" value={formatDurationMs(selectedTool.total_duration_ms)} />
                <KeyValueRow label="错误分类" value={selectedTool.error_category || '--'} />
                <KeyValueRow label="错误信息" value={selectedTool.error_message || '--'} />
              </div>
              <div className="rounded-xl bg-surface-primary p-4">
                <div className="text-sm font-medium text-content-primary">审批历史</div>
                <div className="mt-3 space-y-3">
                  {selectedTool.approval_events.length ? selectedTool.approval_events.map((event) => (
                    <div key={event.id} className="rounded-xl border border-edge px-3 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className={`inline-flex rounded-full border px-2 py-1 text-xs ${statusBadgeClass(event.event_type)}`}>
                          {event.event_type}
                        </span>
                        <span className="text-xs text-content-muted">{formatDateTime(event.occurred_at)}</span>
                      </div>
                      <div className="mt-2 text-sm text-content-secondary">{event.reason || '--'}</div>
                    </div>
                  )) : (
                    <div className="text-sm text-content-muted">没有审批事件。</div>
                  )}
                </div>
              </div>
            </DetailPanel>
          ) : null}
        </div>

        <div className="mt-8 grid gap-6 xl:grid-cols-2">
          <TrendCard
            title="工具失败走势"
            value={overview ? formatCount(overview.tools.failed_call_count) : '--'}
            hint="工具失败随时间分布"
            points={toolFailureTrend}
            color="#b91c1c"
          />
          <TrendCard
            title="审批拒绝走势"
            value={overview ? formatCount(overview.tools.approval_denied_count) : '--'}
            hint="审批拒绝随时间分布"
            points={toolDeniedTrend}
            color="#c2410c"
          />
        </div>
      </div>
    </div>
  )
}
