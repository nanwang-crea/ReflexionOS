/**
 * 文件功能：conversationApi 的单元测试
 * 文件描述：验证 conversationApi.getConversation / getConversationPaginated 能否正确将
 *          后端 snake_case 快照 DTO 转换为前端 camelCase 领域模型，并正确处理分页参数。
 * 核心逻辑：通过 vi.mock 模拟 apiClient.get，构造符合后端格式的响应数据，
 *          断言转换后的返回值与请求参数是否符合预期。
 */
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
    // 场景：后端返回完整的快照（session/turns/runs/messages 均有数据），
    // 验证 conversationApi.getConversation 转换后字段全部变为 camelCase
    getMock.mockResolvedValue({
      data: {
        session: {
          id: 'session-1',
          project_id: 'project-1',
          title: '会话',
          preferred_provider_id: 'provider-a',
          preferred_model_id: null,
          agent_mode: 'build',
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
            turn_message_index: 1,
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
        has_more: false,
        next_before_turn_id: 'turn-1',
      },
    })

    const { conversationApi } = await import('../api/conversation.api')
    const response = await conversationApi.getConversation('session-1')

    expect(getMock).toHaveBeenCalledWith('/api/sessions/session-1/conversation', { params: { limit: 20 } })
    expect(response.data).toEqual({
      session: {
        id: 'session-1',
        projectId: 'project-1',
        title: '会话',
        preferredProviderId: 'provider-a',
        preferredModelId: undefined,
        agentMode: 'build',
        permissionMode: 'auto',
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
          turnMessageIndex: 1,
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
      hasMore: false,
      nextBeforeTurnId: 'turn-1',
    })
  })

  it('falls back to build mode when session agent_mode is unknown', async () => {
    // 场景：后端返回未知的 agent_mode 值，验证前端会兜底为 'build' 模式
    getMock.mockResolvedValue({
      data: {
        session: {
          id: 'session-1',
          project_id: 'project-1',
          title: '会话',
          agent_mode: 'unknown',
          last_event_seq: 2,
          active_turn_id: null,
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:02Z',
        },
        turns: [],
        runs: [],
        messages: [],
        has_more: false,
        next_before_turn_id: null,
      },
    })

    const { conversationApi } = await import('../api/conversation.api')
    const response = await conversationApi.getConversation('session-1')

    expect(response.data.session.agentMode).toBe('build')
  })

  it('serializes before_turn for paginated conversation requests', async () => {
    // 场景：调用分页接口 getConversationPaginated，验证 limit/beforeTurn 会正确
    // 序列化为查询参数 limit/before_turn，且返回的 nextBeforeTurnId 被正确转换
    getMock.mockResolvedValue({
      data: {
        session: {
          id: 'session-1',
          project_id: 'project-1',
          title: '会话',
          last_event_seq: 2,
          active_turn_id: 'turn-2',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:02Z',
        },
        turns: [],
        runs: [],
        messages: [],
        has_more: true,
        next_before_turn_id: 'turn-3',
      },
    })

    const { conversationApi } = await import('../api/conversation.api')
    const response = await conversationApi.getConversationPaginated('session-1', { limit: 20, beforeTurn: 'turn-4' })

    expect(getMock).toHaveBeenCalledWith('/api/sessions/session-1/conversation', {
      params: {
        limit: '20',
        before_turn: 'turn-4',
      },
    })
    expect(response.data.nextBeforeTurnId).toBe('turn-3')
  })
})
