import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from './sessionStore'

const createSessionMock = vi.fn()
const updateSessionMock = vi.fn()
const deleteSessionMock = vi.fn()
const listProjectSessionsMock = vi.fn()

vi.mock('./sessionApi', () => ({
  sessionApi: {
    createSession: createSessionMock,
    updateSession: updateSessionMock,
    deleteSession: deleteSessionMock,
    listProjectSessions: listProjectSessionsMock,
  },
}))

describe('sessionActions', () => {
  beforeEach(() => {
    createSessionMock.mockReset()
    updateSessionMock.mockReset()
    deleteSessionMock.mockReset()
    listProjectSessionsMock.mockReset()
    listProjectSessionsMock.mockResolvedValue({ data: [] })
    useSessionStore.setState({
      sessionsByProjectId: {},
    })
  })

  it('creates a session and stores it under the project', async () => {
    createSessionMock.mockResolvedValue({
      data: {
        id: 'session-1',
        projectId: 'project-1',
        title: '新建聊天',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
    })
    listProjectSessionsMock.mockResolvedValue({
      data: [{
        id: 'session-1',
        projectId: 'project-1',
        title: '新建聊天',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      }],
    })

    const { createSession } = await import('./sessionActions')
    const session = await createSession('project-1', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })

    expect(createSessionMock).toHaveBeenCalledWith('project-1', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })
    expect(listProjectSessionsMock).toHaveBeenCalledWith('project-1')
    expect(session.id).toBe('session-1')
    expect(useSessionStore.getState().sessionsByProjectId['project-1']).toEqual([session])
  })

  it('renames a session through the api and updates sessionStore', async () => {
    useSessionStore.getState().setProjectSessions('project-1', [{
      id: 'session-1',
      projectId: 'project-1',
      title: '旧标题',
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    }])
    updateSessionMock.mockResolvedValue({
      data: {
        id: 'session-1',
        projectId: 'project-1',
        title: '新标题',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      },
    })
    listProjectSessionsMock.mockResolvedValue({
      data: [{
        id: 'session-1',
        projectId: 'project-1',
        title: '新标题',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      }],
    })

    const { renameSession } = await import('./sessionActions')
    const session = await renameSession('session-1', '新标题')

    expect(updateSessionMock).toHaveBeenCalledWith('session-1', { title: '新标题' })
    expect(listProjectSessionsMock).toHaveBeenCalledWith('project-1')
    expect(listProjectSessionsMock).not.toHaveBeenCalledWith('project-2')
    expect(session.title).toBe('新标题')
    expect(useSessionStore.getState().sessionsByProjectId['project-1'][0]?.title).toBe('新标题')
  })

  it('writes session preferences through a dedicated narrow action', async () => {
    useSessionStore.getState().setProjectSessions('project-1', [{
      id: 'session-1',
      projectId: 'project-1',
      title: '现有会话',
      preferredProviderId: 'provider-old',
      preferredModelId: 'model-old',
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    }])
    updateSessionMock.mockResolvedValue({
      data: {
        id: 'session-1',
        projectId: 'project-1',
        title: '现有会话',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      },
    })
    listProjectSessionsMock.mockResolvedValue({
      data: [{
        id: 'session-1',
        projectId: 'project-1',
        title: '现有会话',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      }],
    })

    const { writeSessionPreferences } = await import('./sessionActions')
    const session = await writeSessionPreferences('session-1', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })

    expect(updateSessionMock).toHaveBeenCalledWith('session-1', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })
    expect(listProjectSessionsMock).toHaveBeenCalledWith('project-1')
    expect(session.preferredProviderId).toBe('provider-a')
    expect(session.preferredModelId).toBe('model-a')
  })

  it('deletes a session through the api and removes it from sessionStore', async () => {
    useSessionStore.getState().setProjectSessions('project-1', [{
      id: 'session-1',
      projectId: 'project-1',
      title: '删除会话',
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    }])

    const { deleteSession } = await import('./sessionActions')
    await deleteSession('project-1', 'session-1')

    expect(deleteSessionMock).toHaveBeenCalledWith('session-1')
    expect(listProjectSessionsMock).toHaveBeenCalledWith('project-1')
    expect(listProjectSessionsMock).not.toHaveBeenCalledWith('project-2')
    expect(useSessionStore.getState().sessionsByProjectId['project-1']).toEqual([])
  })

})
