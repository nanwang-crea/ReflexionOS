import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from './sessionStore'

const createSessionMock = vi.fn()
const updateSessionMock = vi.fn()
const deleteSessionMock = vi.fn()

vi.mock('./sessionApi', () => ({
  sessionApi: {
    createSession: createSessionMock,
    updateSession: updateSessionMock,
    deleteSession: deleteSessionMock,
  },
}))

describe('sessionActions', () => {
  beforeEach(() => {
    createSessionMock.mockReset()
    updateSessionMock.mockReset()
    deleteSessionMock.mockReset()
    useSessionStore.setState({
      sessionsByProjectId: {},
      historyBySessionId: {},
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

    const { createSession } = await import('./sessionActions')
    const session = await createSession('project-1', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })

    expect(createSessionMock).toHaveBeenCalledWith('project-1', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })
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

    const { renameSession } = await import('./sessionActions')
    const session = await renameSession('session-1', '新标题')

    expect(updateSessionMock).toHaveBeenCalledWith('session-1', { title: '新标题' })
    expect(session.title).toBe('新标题')
    expect(useSessionStore.getState().sessionsByProjectId['project-1'][0]?.title).toBe('新标题')
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
    expect(useSessionStore.getState().sessionsByProjectId['project-1']).toEqual([])
  })
})
