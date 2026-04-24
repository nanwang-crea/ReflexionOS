import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSessionStore } from './sessionStore'

const getMock = vi.fn()
const postMock = vi.fn()
const patchMock = vi.fn()
const deleteMock = vi.fn()

vi.mock('@/services/apiClient', () => ({
  apiClient: {
    get: getMock,
    post: postMock,
    patch: patchMock,
    delete: deleteMock,
  },
}))

beforeEach(() => {
  vi.resetModules()
  getMock.mockReset()
  postMock.mockReset()
  patchMock.mockReset()
  deleteMock.mockReset()
})

describe('createSessionStore', () => {
  it('stores sessions by project id', () => {
    const store = createSessionStore()

    store.getState().setProjectSessions('project-1', [
      {
        id: 'session-1',
        projectId: 'project-1',
        title: '新建聊天',
        preferredProviderId: undefined,
        preferredModelId: undefined,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
    ])

    expect(store.getState().sessionsByProjectId['project-1']).toEqual([
      {
        id: 'session-1',
        projectId: 'project-1',
        title: '新建聊天',
        preferredProviderId: undefined,
        preferredModelId: undefined,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
    ])
  })

  it('upserts a session by replacing an existing session and prepending a new one', () => {
    const store = createSessionStore()

    store.getState().setProjectSessions('project-1', [
      {
        id: 'session-1',
        projectId: 'project-1',
        title: '旧标题',
        preferredProviderId: undefined,
        preferredModelId: undefined,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
    ])

    store.getState().upsertSession('project-1', {
      id: 'session-1',
      projectId: 'project-1',
      title: '新标题',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:01:00Z',
    })
    store.getState().upsertSession('project-1', {
      id: 'session-2',
      projectId: 'project-1',
      title: '第二个会话',
      preferredProviderId: undefined,
      preferredModelId: undefined,
      createdAt: '2026-04-20T00:02:00Z',
      updatedAt: '2026-04-20T00:02:00Z',
    })

    expect(store.getState().sessionsByProjectId['project-1']).toEqual([
      {
        id: 'session-2',
        projectId: 'project-1',
        title: '第二个会话',
        preferredProviderId: undefined,
        preferredModelId: undefined,
        createdAt: '2026-04-20T00:02:00Z',
        updatedAt: '2026-04-20T00:02:00Z',
      },
      {
        id: 'session-1',
        projectId: 'project-1',
        title: '新标题',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      },
    ])
  })

  it('removes a session from project cache', () => {
    const store = createSessionStore()

    store.getState().setProjectSessions('project-1', [
      {
        id: 'session-1',
        projectId: 'project-1',
        title: '保留会话',
        preferredProviderId: undefined,
        preferredModelId: undefined,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
      {
        id: 'session-2',
        projectId: 'project-1',
        title: '删除会话',
        preferredProviderId: undefined,
        preferredModelId: undefined,
        createdAt: '2026-04-20T00:01:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      },
    ])

    store.getState().removeSession('project-1', 'session-2')

    expect(store.getState().sessionsByProjectId['project-1']).toEqual([
      {
        id: 'session-1',
        projectId: 'project-1',
        title: '保留会话',
        preferredProviderId: undefined,
        preferredModelId: undefined,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
    ])
  })
})

describe('sessionApi', () => {
  it('maps backend session summaries into frontend session summaries', async () => {
    getMock.mockResolvedValue({
      data: [
        {
          id: 'session-1',
          project_id: 'project-1',
          title: '新建聊天',
          preferred_provider_id: 'provider-a',
          preferred_model_id: 'model-a',
          created_at: '2026-04-20T00:00:00Z',
          updated_at: '2026-04-20T00:00:00Z',
        },
      ],
    })

    const { sessionApi } = await import('./sessionApi')
    const response = await sessionApi.listProjectSessions('project-1')

    expect(getMock).toHaveBeenCalledWith('/api/projects/project-1/sessions')
    expect(response.data).toEqual([
      {
        id: 'session-1',
        projectId: 'project-1',
        title: '新建聊天',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
    ])
  })

  it('normalizes createSession request and response payloads', async () => {
    postMock.mockResolvedValue({
      data: {
        id: 'session-1',
        project_id: 'project-1',
        title: '需求讨论',
        preferred_provider_id: null,
        preferred_model_id: 'model-a',
        created_at: '2026-04-20T00:00:00Z',
        updated_at: '2026-04-20T00:00:00Z',
      },
    })

    const { sessionApi } = await import('./sessionApi')
    const response = await sessionApi.createSession('project-1', {
      title: '需求讨论',
      preferredProviderId: undefined,
      preferredModelId: 'model-a',
    })

    expect(postMock).toHaveBeenCalledWith('/api/projects/project-1/sessions', {
      title: '需求讨论',
      preferred_model_id: 'model-a',
    })
    expect(response.data).toEqual({
      id: 'session-1',
      projectId: 'project-1',
      title: '需求讨论',
      preferredProviderId: undefined,
      preferredModelId: 'model-a',
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    })
  })

  it('normalizes updateSession request and response payloads with null values', async () => {
    patchMock.mockResolvedValue({
      data: {
        id: 'session-1',
        project_id: 'project-1',
        title: '只改模型',
        preferred_provider_id: 'provider-b',
        preferred_model_id: null,
        created_at: '2026-04-20T00:00:00Z',
        updated_at: '2026-04-20T00:05:00Z',
      },
    })

    const { sessionApi } = await import('./sessionApi')
    const response = await sessionApi.updateSession('session-1', {
      preferredProviderId: 'provider-b',
      preferredModelId: null,
    })

    expect(patchMock).toHaveBeenCalledWith('/api/sessions/session-1', {
      preferred_provider_id: 'provider-b',
      preferred_model_id: null,
    })
    expect(response.data).toEqual({
      id: 'session-1',
      projectId: 'project-1',
      title: '只改模型',
      preferredProviderId: 'provider-b',
      preferredModelId: undefined,
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:05:00Z',
    })
  })

  it('calls delete session endpoint', async () => {
    deleteMock.mockResolvedValue({ data: { message: '会话已删除' } })

    const { sessionApi } = await import('./sessionApi')
    await sessionApi.deleteSession('session-1')

    expect(deleteMock).toHaveBeenCalledWith('/api/sessions/session-1')
  })
})
