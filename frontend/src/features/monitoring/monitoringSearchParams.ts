export interface MonitoringSearchState {
  projectId: string
  windowHours: number
  requestStatusFilter: string
  requestCostStatusFilter: string
  toolStatusFilter: string
  toolTerminalReasonFilter: string
  selectedRequestId: string | null
  selectedToolId: string | null
}

export const DEFAULT_MONITORING_SEARCH_STATE: MonitoringSearchState = {
  projectId: 'all',
  windowHours: 24,
  requestStatusFilter: 'all',
  requestCostStatusFilter: 'all',
  toolStatusFilter: 'all',
  toolTerminalReasonFilter: 'all',
  selectedRequestId: null,
  selectedToolId: null,
}

function readString(params: URLSearchParams, key: string, fallback: string) {
  const value = params.get(key)
  return value && value.trim() ? value : fallback
}

function readNullableString(params: URLSearchParams, key: string) {
  const value = params.get(key)
  return value && value.trim() ? value : null
}

function readWindowHours(params: URLSearchParams) {
  const value = Number(params.get('window'))
  if (!Number.isFinite(value) || value < 1 || value > 24 * 30) {
    return DEFAULT_MONITORING_SEARCH_STATE.windowHours
  }
  return Math.floor(value)
}

export function parseMonitoringSearchState(
  params: URLSearchParams,
): MonitoringSearchState {
  return {
    projectId: readString(
      params,
      'project',
      DEFAULT_MONITORING_SEARCH_STATE.projectId,
    ),
    windowHours: readWindowHours(params),
    requestStatusFilter: readString(
      params,
      'requestStatus',
      DEFAULT_MONITORING_SEARCH_STATE.requestStatusFilter,
    ),
    requestCostStatusFilter: readString(
      params,
      'requestCost',
      DEFAULT_MONITORING_SEARCH_STATE.requestCostStatusFilter,
    ),
    toolStatusFilter: readString(
      params,
      'toolStatus',
      DEFAULT_MONITORING_SEARCH_STATE.toolStatusFilter,
    ),
    toolTerminalReasonFilter: readString(
      params,
      'toolReason',
      DEFAULT_MONITORING_SEARCH_STATE.toolTerminalReasonFilter,
    ),
    selectedRequestId: readNullableString(params, 'requestId'),
    selectedToolId: readNullableString(params, 'toolId'),
  }
}

export function buildMonitoringSearchParams(
  state: MonitoringSearchState,
): URLSearchParams {
  const params = new URLSearchParams()

  if (state.projectId !== DEFAULT_MONITORING_SEARCH_STATE.projectId) {
    params.set('project', state.projectId)
  }
  if (state.windowHours !== DEFAULT_MONITORING_SEARCH_STATE.windowHours) {
    params.set('window', String(state.windowHours))
  }
  if (
    state.requestStatusFilter !==
    DEFAULT_MONITORING_SEARCH_STATE.requestStatusFilter
  ) {
    params.set('requestStatus', state.requestStatusFilter)
  }
  if (
    state.requestCostStatusFilter !==
    DEFAULT_MONITORING_SEARCH_STATE.requestCostStatusFilter
  ) {
    params.set('requestCost', state.requestCostStatusFilter)
  }
  if (state.toolStatusFilter !== DEFAULT_MONITORING_SEARCH_STATE.toolStatusFilter) {
    params.set('toolStatus', state.toolStatusFilter)
  }
  if (
    state.toolTerminalReasonFilter !==
    DEFAULT_MONITORING_SEARCH_STATE.toolTerminalReasonFilter
  ) {
    params.set('toolReason', state.toolTerminalReasonFilter)
  }
  if (state.selectedRequestId) {
    params.set('requestId', state.selectedRequestId)
  }
  if (state.selectedToolId) {
    params.set('toolId', state.selectedToolId)
  }

  return params
}
