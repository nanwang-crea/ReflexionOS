/**
 * 文件功能：session.actions.ts 单元测试
 * 文件描述：验证创建/重命名/写偏好/重置/删除会话等动作是否正确调用 sessionApi，
 *           并正确将结果同步到 session.store 缓存中。
 * 核心逻辑：对 ../api/session.api 做 mock，用 vi.fn 断言调用参数，
 *           再读取 useSessionStore 的状态断言缓存内容是否符合预期。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionStore } from '@/features/sessions/stores/session.store'

const createSessionMock = vi.fn()
const updateSessionMock = vi.fn()
const resetSessionMock = vi.fn()
const deleteSessionMock = vi.fn()
const listProjectSessionsMock = vi.fn()

vi.mock('../api/session.api', () => ({
  sessionApi: {
    createSession: createSessionMock,
    updateSession: updateSessionMock,
    resetSession: resetSessionMock,
    deleteSession: deleteSessionMock,
    listProjectSessions: listProjectSessionsMock,
  },
}))

describe('sessionActions', () => {
  beforeEach(() => {
    createSessionMock.mockReset()
    updateSessionMock.mockReset()
    resetSessionMock.mockReset()
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
        lastEventSeq: 0,
        activeTurnId: null,
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
        lastEventSeq: 0,
        activeTurnId: null,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      }],
    })

    const { createSession } = await import('../session.actions')
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
      lastEventSeq: 0,
      activeTurnId: null,
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    }])
    updateSessionMock.mockResolvedValue({
      data: {
        id: 'session-1',
        projectId: 'project-1',
        title: '新标题',
        lastEventSeq: 0,
        activeTurnId: null,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      },
    })
    listProjectSessionsMock.mockResolvedValue({
      data: [{
        id: 'session-1',
        projectId: 'project-1',
        title: '新标题',
        lastEventSeq: 0,
        activeTurnId: null,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      }],
    })

    const { renameSession } = await import('../session.actions')
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
      lastEventSeq: 0,
      activeTurnId: null,
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
        lastEventSeq: 0,
        activeTurnId: null,
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
        lastEventSeq: 0,
        activeTurnId: null,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      }],
    })

    const { writeSessionPreferences } = await import('../session.actions')
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

  it('resets a session through the api and upserts the cleared session into sessionStore', async () => {
    useSessionStore.getState().setProjectSessions('project-1', [{
      id: 'session-1',
      projectId: 'project-1',
      title: '会话',
      lastEventSeq: 120,
      activeTurnId: 'turn-9',
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    }])
    resetSessionMock.mockResolvedValue({
      data: {
        id: 'session-1',
        projectId: 'project-1',
        title: '会话',
        lastEventSeq: 0,
        activeTurnId: null,
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:02:00Z',
      },
    })

    const { resetSession } = await import('../session.actions')
    const session = await resetSession('session-1')

    expect(resetSessionMock).toHaveBeenCalledWith('session-1')
    // 用返回的 Session 回写列表真值：计数清零、活跃 turn 清空，标题/位置保留。
    const stored = useSessionStore.getState().sessionsByProjectId['project-1'][0]
    expect(stored.id).toBe('session-1')
    expect(stored.title).toBe('会话')
    expect(stored.lastEventSeq).toBe(0)
    expect(stored.activeTurnId).toBeNull()
    expect(session.lastEventSeq).toBe(0)
  })

  it('deletes a session through the api and removes it from sessionStore', async () => {
    useSessionStore.getState().setProjectSessions('project-1', [{
      id: 'session-1',
      projectId: 'project-1',
      title: '删除会话',
      lastEventSeq: 0,
      activeTurnId: null,
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    }])

    const { deleteSession } = await import('../session.actions')
    await deleteSession('project-1', 'session-1')

    expect(deleteSessionMock).toHaveBeenCalledWith('session-1')
    expect(listProjectSessionsMock).toHaveBeenCalledWith('project-1')
    expect(listProjectSessionsMock).not.toHaveBeenCalledWith('project-2')
    expect(useSessionStore.getState().sessionsByProjectId['project-1']).toEqual([])
  })

})
