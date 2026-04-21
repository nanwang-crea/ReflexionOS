import type { AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from './sessionStore'
import { sessionApi } from './sessionApi'
import { ensureSessionHistoryLoaded } from './sessionLoader'
import * as sessionHistoryRound from './sessionHistoryRound'

const receiptDetail = {
  id: 'detail-1',
  toolName: 'shell',
  status: 'failed' as const,
  summary: 'Shell command failed',
  category: 'command' as const,
  error: 'boom',
}

vi.mock('./sessionApi', () => ({
  sessionApi: {
    getSessionHistory: vi.fn(),
  },
}))

describe('ensureSessionHistoryLoaded', () => {
  beforeEach(() => {
    useSessionStore.setState({
      sessionsByProjectId: {},
      historyBySessionId: {},
    })
    vi.mocked(sessionApi.getSessionHistory).mockReset()
  })

  it('writes backend round history into sessionStore without archive regrouping', async () => {
    const normalizeRoundFromApiSpy = vi.spyOn(sessionHistoryRound, 'normalizeRoundFromApi')

    const response: AxiosResponse<Awaited<ReturnType<typeof sessionApi.getSessionHistory>>['data']> = {
      data: {
        sessionId: 'session-1',
        projectId: 'project-1',
        rounds: [
          {
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
          },
        ],
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: { headers: {} as never },
    }

    vi.mocked(sessionApi.getSessionHistory).mockResolvedValue(response)

    await ensureSessionHistoryLoaded('session-1')

    expect(sessionApi.getSessionHistory).toHaveBeenCalledWith('session-1')
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
})
