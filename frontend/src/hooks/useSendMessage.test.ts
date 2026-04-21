import { describe, expect, it, vi } from 'vitest'
import type { SessionSummary } from '@/types/workspace'
import { createSendMessage } from './useSendMessage'

describe('createSendMessage', () => {
  it('creates a backend session before first send when no current session exists', async () => {
    const createdSession: SessionSummary = {
      id: 'session-1',
      projectId: 'project-1',
      title: '新建聊天',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      createdAt: '2026-04-21T00:00:00Z',
      updatedAt: '2026-04-21T00:00:00Z',
    }
    const createSession = vi.fn().mockResolvedValue(createdSession)
    const writeSessionPreferences = vi.fn()
    const startExecutionRun = vi.fn().mockResolvedValue(undefined)
    const notify = vi.fn()

    const sendMessage = createSendMessage({
      currentProject: { id: 'project-1', name: 'Project', path: '/tmp/project' },
      currentSession: null,
      configured: true,
      selection: { providerId: 'provider-a', modelId: 'model-a' },
      createSession,
      writeSessionPreferences,
      startExecutionRun,
      notify,
    })

    await sendMessage('hello')

    expect(createSession).toHaveBeenCalledWith('project-1', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })
    expect(writeSessionPreferences).not.toHaveBeenCalled()
    expect(startExecutionRun).toHaveBeenCalledWith({
      sessionId: 'session-1',
      message: 'hello',
      projectId: 'project-1',
      providerId: 'provider-a',
      modelId: 'model-a',
    })
    expect(notify).not.toHaveBeenCalled()
  })

  it('reuses the current session and refreshes preferences before sending', async () => {
    const createSession = vi.fn()
    const writeSessionPreferences = vi.fn().mockResolvedValue(undefined)
    const startExecutionRun = vi.fn().mockResolvedValue(undefined)

    const sendMessage = createSendMessage({
      currentProject: { id: 'project-1', name: 'Project', path: '/tmp/project' },
      currentSession: {
        id: 'session-2',
        projectId: 'project-1',
        title: 'Existing',
        preferredProviderId: 'provider-old',
        preferredModelId: 'model-old',
        createdAt: '2026-04-21T00:00:00Z',
        updatedAt: '2026-04-21T00:00:00Z',
      },
      configured: true,
      selection: { providerId: 'provider-a', modelId: 'model-a' },
      createSession,
      writeSessionPreferences,
      startExecutionRun,
      notify: vi.fn(),
    })

    await sendMessage('ship it')

    expect(createSession).not.toHaveBeenCalled()
    expect(writeSessionPreferences).toHaveBeenCalledWith('session-2', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })
    expect(startExecutionRun).toHaveBeenCalledWith({
      sessionId: 'session-2',
      message: 'ship it',
      projectId: 'project-1',
      providerId: 'provider-a',
      modelId: 'model-a',
    })
  })

  it('does not require persisted rounds on the current session summary', async () => {
    const writeSessionPreferences = vi.fn().mockResolvedValue(undefined)
    const startExecutionRun = vi.fn().mockResolvedValue(undefined)

    const sendMessage = createSendMessage({
      currentProject: { id: 'project-1', name: 'Project', path: '/tmp/project' },
      currentSession: {
        id: 'session-3',
        projectId: 'project-1',
        title: 'Summary only',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        createdAt: '2026-04-21T00:00:00Z',
        updatedAt: '2026-04-21T00:00:00Z',
      },
      configured: true,
      selection: { providerId: 'provider-a', modelId: 'model-a' },
      createSession: vi.fn(),
      writeSessionPreferences,
      startExecutionRun,
      notify: vi.fn(),
    })

    await sendMessage('summary boundary')

    expect(writeSessionPreferences).toHaveBeenCalledWith('session-3', {
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
    })
    expect(startExecutionRun).toHaveBeenCalledWith({
      sessionId: 'session-3',
      message: 'summary boundary',
      projectId: 'project-1',
      providerId: 'provider-a',
      modelId: 'model-a',
    })
  })
})
