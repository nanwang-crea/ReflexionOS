import type { AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from './sessionStore'
import { ensureSessionHistoryLoaded, refreshSessionHistory } from './sessionLoader'
import * as sessionHistoryRound from './sessionHistoryRound'
import { apiClient } from '@/services/apiClient'

const receiptDetail = {
  id: 'detail-1',
  toolName: 'shell',
  status: 'failed' as const,
  summary: 'Shell command failed',
  category: 'command' as const,
  error: 'boom',
}

function buildHistoryResponse(rounds: Array<{
  id: string
  created_at: string
  items: Array<{
    id: string
    type: 'user-message' | 'assistant-message' | 'agent-update' | 'action-receipt'
    content: string
    receipt_status?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | null
    details: typeof receiptDetail[]
    created_at: string
  }>
}>): AxiosResponse<{
  session_id: string
  project_id: string | null
  rounds: typeof rounds
}> {
  return {
    data: {
      session_id: 'session-1',
      project_id: 'project-1',
      rounds,
    },
    status: 200,
    statusText: 'OK',
    headers: {},
    config: { headers: {} as never },
  }
}

vi.mock('@/services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

describe('ensureSessionHistoryLoaded', () => {
  beforeEach(() => {
    useSessionStore.setState({
      sessionsByProjectId: {},
      historyBySessionId: {},
    })
    vi.mocked(apiClient.get).mockReset()
  })

  it('loads session history through sessionApi and writes normalized rounds into sessionStore', async () => {
    const normalizeRoundFromApiSpy = vi.spyOn(sessionHistoryRound, 'normalizeRoundFromApi')

    const response = buildHistoryResponse([
      {
        id: 'round-1',
        created_at: '2026-04-20T00:00:00Z',
        items: [
          {
            id: 'item-1',
            type: 'user-message',
            content: 'hi',
            details: [],
            created_at: '2026-04-20T00:00:00Z',
          },
          {
            id: 'item-2',
            type: 'action-receipt',
            content: '',
            receipt_status: 'failed',
            details: [receiptDetail],
            created_at: '2026-04-20T00:00:01Z',
          },
          {
            id: 'item-3',
            type: 'agent-update',
            content: 'Running tools',
            details: [],
            created_at: '2026-04-20T00:00:02Z',
          },
        ],
      },
    ])

    vi.mocked(apiClient.get).mockResolvedValue(response)

    await ensureSessionHistoryLoaded('session-1')

    expect(apiClient.get).toHaveBeenCalledWith('/api/sessions/session-1/history')
    expect(normalizeRoundFromApiSpy).toHaveBeenCalledWith({
      id: 'round-1',
      createdAt: '2026-04-20T00:00:00Z',
      items: [
        {
          id: 'item-1',
          type: 'user-message',
          content: 'hi',
          details: [],
          createdAt: '2026-04-20T00:00:00Z',
        },
        {
          id: 'item-2',
          type: 'action-receipt',
          content: '',
          receiptStatus: 'failed',
          details: [receiptDetail],
          createdAt: '2026-04-20T00:00:01Z',
        },
        {
          id: 'item-3',
          type: 'agent-update',
          content: 'Running tools',
          details: [],
          createdAt: '2026-04-20T00:00:02Z',
        },
      ],
    })
    expect(useSessionStore.getState().historyBySessionId['session-1']).toEqual([
      {
        id: 'round-1',
        createdAt: '2026-04-20T00:00:00Z',
        items: [
          { id: 'item-1', type: 'user-message', content: 'hi' },
          {
            id: 'item-2',
            type: 'action-receipt',
            receiptStatus: 'failed',
            details: [receiptDetail],
          },
          {
            id: 'item-3',
            type: 'agent-update',
            content: 'Running tools',
          },
        ],
      },
    ])

    normalizeRoundFromApiSpy.mockRestore()
  })

  it('does not refetch when session history is already cached', async () => {
    useSessionStore.getState().setSessionHistory('session-1', [{
      id: 'cached-round',
      createdAt: '2026-04-20T00:00:00Z',
      items: [],
    }])

    await ensureSessionHistoryLoaded('session-1')

    expect(apiClient.get).not.toHaveBeenCalled()
    expect(useSessionStore.getState().historyBySessionId['session-1']).toEqual([
      {
        id: 'cached-round',
        createdAt: '2026-04-20T00:00:00Z',
        items: [],
      },
    ])
  })
})

describe('refreshSessionHistory', () => {
  beforeEach(() => {
    useSessionStore.setState({
      sessionsByProjectId: {},
      historyBySessionId: {},
    })
    vi.mocked(apiClient.get).mockReset()
  })

  it('always refetches and replaces cached rounds', async () => {
    useSessionStore.getState().setSessionHistory('session-1', [{
      id: 'stale-round',
      createdAt: '2026-04-19T00:00:00Z',
      items: [],
    }])

    const response = buildHistoryResponse([
      {
        id: 'fresh-round',
        created_at: '2026-04-20T00:00:00Z',
        items: [],
      },
    ])

    vi.mocked(apiClient.get).mockResolvedValue(response)

    await refreshSessionHistory('session-1')

    expect(apiClient.get).toHaveBeenCalledTimes(1)
    expect(apiClient.get).toHaveBeenCalledWith('/api/sessions/session-1/history')
    expect(useSessionStore.getState().historyBySessionId['session-1']).toEqual([
      {
        id: 'fresh-round',
        createdAt: '2026-04-20T00:00:00Z',
        items: [],
      },
    ])
  })
})
