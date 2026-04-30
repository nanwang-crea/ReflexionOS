import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSidebarSessionActions } from './useSidebarSessionActions'
import type { Project } from '@/types/project'
import type { DialogService } from '@/services/dialogService'

function createProject(id: string): Project {
  return {
    id,
    name: id,
    path: `/tmp/${id}`,
    language: 'typescript',
    created_at: '2026-04-19T00:00:00.000Z',
    updated_at: '2026-04-19T00:00:00.000Z',
  }
}

function createDialogService(overrides: Partial<DialogService> = {}): DialogService {
  return {
    notifyError: vi.fn(),
    confirmAction: vi.fn(() => true),
    promptText: vi.fn(() => null),
    ...overrides,
  }
}

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

describe('useSidebarSessionActions', () => {
  beforeEach(() => {
    createSessionMock.mockReset()
    updateSessionMock.mockReset()
    deleteSessionMock.mockReset()
  })

  it('reports session action failures through the dialog service', async () => {
    createSessionMock.mockRejectedValue(new Error('boom'))
    const dialogService = createDialogService()
    const actions = useSidebarSessionActions({
      busy: false,
      projects: [createProject('project-1')],
      currentProject: createProject('project-1'),
      currentSessionId: null,
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setCurrentSessionId: vi.fn(),
      setShowProjectModal: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleCreateSession()

    expect(dialogService.notifyError).toHaveBeenCalledWith('创建聊天失败')
  })

  it('prompts for session rename through the dialog service', async () => {
    updateSessionMock.mockResolvedValue(undefined)
    const dialogService = createDialogService({
      promptText: vi.fn(() => '新的标题'),
    })
    const actions = useSidebarSessionActions({
      busy: false,
      projects: [createProject('project-1')],
      currentProject: createProject('project-1'),
      currentSessionId: 'session-1',
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setCurrentSessionId: vi.fn(),
      setShowProjectModal: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleRenameSession({
      id: 'session-1',
      projectId: 'project-1',
      title: '旧标题',
      createdAt: '2026-04-20T00:00:00Z',
      updatedAt: '2026-04-20T00:00:00Z',
    })

    expect(dialogService.promptText).toHaveBeenCalledWith('重命名聊天', '旧标题')
    expect(updateSessionMock).toHaveBeenCalledWith('session-1', '新的标题')
  })
})
