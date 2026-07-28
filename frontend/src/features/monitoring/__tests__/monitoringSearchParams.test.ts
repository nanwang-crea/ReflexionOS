import { describe, expect, it } from 'vitest'
import {
  buildMonitoringSearchParams,
  DEFAULT_MONITORING_SEARCH_STATE,
  parseMonitoringSearchState,
} from '../monitoringSearchParams'

describe('monitoringSearchParams', () => {
  it('parses defaults when query is empty or invalid', () => {
    const params = new URLSearchParams('window=-1&requestStatus=&toolId=')

    expect(parseMonitoringSearchState(params)).toEqual(
      DEFAULT_MONITORING_SEARCH_STATE,
    )
  })

  it('parses explicit state from URLSearchParams', () => {
    const params = new URLSearchParams(
      'project=project-1&window=168&requestStatus=failed&requestCost=unpriced&toolStatus=failed&toolReason=denied&requestId=req-1',
    )

    expect(parseMonitoringSearchState(params)).toEqual({
      projectId: 'project-1',
      windowHours: 168,
      requestStatusFilter: 'failed',
      requestCostStatusFilter: 'unpriced',
      toolStatusFilter: 'failed',
      toolTerminalReasonFilter: 'denied',
      selectedRequestId: 'req-1',
      selectedToolId: null,
    })
  })

  it('serializes only non-default fields', () => {
    const params = buildMonitoringSearchParams({
      ...DEFAULT_MONITORING_SEARCH_STATE,
      projectId: 'project-1',
      requestStatusFilter: 'failed',
      selectedToolId: 'tool-1',
    })

    expect(params.toString()).toBe(
      'project=project-1&requestStatus=failed&toolId=tool-1',
    )
  })
})
