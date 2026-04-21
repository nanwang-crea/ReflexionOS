import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSidebarSession, deleteSidebarSession } from './useSidebarSessionActions'

const {
  createSessionMock,
  updateSessionMock,
  deleteSessionMock,
} = vi.hoisted(() => ({
  createSessionMock: vi.fn(),
  updateSessionMock: vi.fn(),
  deleteSessionMock: vi.fn(),
}))

vi.mock('@/features/sessions/sessionActions', () => ({
  createSession: createSessionMock,
  renameSession: updateSessionMock,
  deleteSession: deleteSessionMock,
}))

describe('useSidebarSessionActions helpers', () => {
  beforeEach(() => {
    createSessionMock.mockReset()
    updateSessionMock.mockReset()
    deleteSessionMock.mockReset()
  })

  it('delegates session creation through sidebar session actions', async () => {
    createSessionMock.mockResolvedValue({
      id: 'session-2',
      projectId: 'project-1',
      title: '新建聊天',
      preferredProviderId: 'provider-b',
      preferredModelId: 'model-b',
      createdAt: '2026-04-20T00:02:00Z',
      updatedAt: '2026-04-20T00:02:00Z',
    })

    await createSidebarSession({
      projectId: 'project-1',
      defaultProviderId: 'provider-b',
      defaultModelId: 'model-b',
    })

    expect(createSessionMock).toHaveBeenCalledWith('project-1', {
      preferredProviderId: 'provider-b',
      preferredModelId: 'model-b',
    })
  })

  it('clears the current session only when sidebar deletion removes the active session', async () => {
    const setCurrentSessionId = vi.fn()
    deleteSessionMock.mockResolvedValue(undefined)

    await deleteSidebarSession({
      session: {
        id: 'session-1',
        projectId: 'project-1',
        title: '当前聊天',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      },
      currentSessionId: 'session-1',
      setCurrentSessionId,
    })

    expect(deleteSessionMock).toHaveBeenCalledWith('project-1', 'session-1')
    expect(setCurrentSessionId).toHaveBeenCalledWith(null)
  })
})
