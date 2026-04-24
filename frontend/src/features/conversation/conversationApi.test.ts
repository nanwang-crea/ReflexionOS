import { beforeEach, describe, expect, it, vi } from 'vitest'

const getMock = vi.fn()

vi.mock('@/services/apiClient', () => ({
  apiClient: {
    get: getMock,
  },
  buildSessionConversationPath: (sessionId: string) => `/api/sessions/${sessionId}/conversation`,
}))

describe('conversationApi', () => {
  beforeEach(() => {
    vi.resetModules()
    getMock.mockReset()
  })

  it('maps snake_case conversation snapshot to camelCase', async () => {
    getMock.mockResolvedValue({
      data: {
        session: {
          id: 'session-1',
          project_id: 'project-1',
          title: '会话',
          preferred_provider_id: 'provider-a',
          preferred_model_id: null,
          last_event_seq: 2,
          active_turn_id: 'turn-1',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:02Z',
        },
        turns: [
          {
            id: 'turn-1',
            session_id: 'session-1',
            turn_index: 1,
            root_message_id: 'msg-1',
            status: 'running',
            active_run_id: 'run-1',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T10:00:01Z',
            completed_at: null,
          },
        ],
        runs: [
          {
            id: 'run-1',
            session_id: 'session-1',
            turn_id: 'turn-1',
            attempt_index: 1,
            status: 'running',
            provider_id: 'provider-a',
            model_id: 'model-a',
            workspace_ref: '/tmp/reflexion',
            started_at: null,
            finished_at: null,
            error_code: null,
            error_message: null,
          },
        ],
        messages: [
          {
            id: 'msg-1',
            session_id: 'session-1',
            turn_id: 'turn-1',
            run_id: null,
            message_index: 1,
            role: 'user',
            message_type: 'user_message',
            stream_state: 'completed',
            display_mode: 'default',
            content_text: 'hello',
            payload_json: {},
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T10:00:00Z',
            completed_at: '2026-04-24T10:00:00Z',
          },
        ],
      },
    })

    const { conversationApi } = await import('./conversationApi')
    const response = await conversationApi.getConversation('session-1')

    expect(getMock).toHaveBeenCalledWith('/api/sessions/session-1/conversation')
    expect(response.data).toEqual({
      session: {
        id: 'session-1',
        projectId: 'project-1',
        title: '会话',
        preferredProviderId: 'provider-a',
        preferredModelId: undefined,
        lastEventSeq: 2,
        activeTurnId: 'turn-1',
        createdAt: '2026-04-24T10:00:00Z',
        updatedAt: '2026-04-24T10:00:02Z',
      },
      turns: [
        {
          id: 'turn-1',
          sessionId: 'session-1',
          turnIndex: 1,
          rootMessageId: 'msg-1',
          status: 'running',
          activeRunId: 'run-1',
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:01Z',
          completedAt: null,
        },
      ],
      runs: [
        {
          id: 'run-1',
          sessionId: 'session-1',
          turnId: 'turn-1',
          attemptIndex: 1,
          status: 'running',
          providerId: 'provider-a',
          modelId: 'model-a',
          workspaceRef: '/tmp/reflexion',
          startedAt: null,
          finishedAt: null,
          errorCode: null,
          errorMessage: null,
        },
      ],
      messages: [
        {
          id: 'msg-1',
          sessionId: 'session-1',
          turnId: 'turn-1',
          runId: null,
          messageIndex: 1,
          role: 'user',
          messageType: 'user_message',
          streamState: 'completed',
          displayMode: 'default',
          contentText: 'hello',
          payloadJson: {},
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
          completedAt: '2026-04-24T10:00:00Z',
        },
      ],
    })
  })
})
