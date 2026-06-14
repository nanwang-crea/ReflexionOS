import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSidebarSessionActions } from '../useSidebarSessionActions'
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

vi.mock('@/features/sessions/session.actions', () => ({
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

  it('renames session with provided title', async () => {
    updateSessionMock.mockResolvedValue(undefined)
    const dialogService = createDialogService()
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

    await actions.handleRenameSession('session-1', '新的标题')

    expect(updateSessionMock).toHaveBeenCalledWith('session-1', '新的标题')
  })
})
