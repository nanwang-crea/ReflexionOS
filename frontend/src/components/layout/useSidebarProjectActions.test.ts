import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSidebarProjectActions } from './useSidebarProjectActions'
import type { DialogService } from '@/services/dialogService'
import type { Project } from '@/types/project'

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
  createProjectApiMock,
  deleteProjectApiMock,
  selectProjectDirectoryMock,
} = vi.hoisted(() => ({
  createProjectApiMock: vi.fn(),
  deleteProjectApiMock: vi.fn(),
  selectProjectDirectoryMock: vi.fn(),
}))

vi.mock('@/services/apiClient', () => ({
  projectApi: {
    create: createProjectApiMock,
    delete: deleteProjectApiMock,
  },
}))

vi.mock('@/services/desktopClient', () => ({
  selectProjectDirectory: selectProjectDirectoryMock,
}))

describe('useSidebarProjectActions', () => {
  beforeEach(() => {
    createProjectApiMock.mockReset()
    deleteProjectApiMock.mockReset()
    selectProjectDirectoryMock.mockReset()
  })

  it('deletes a project and clears current selection when needed', async () => {
    deleteProjectApiMock.mockResolvedValue(undefined)
    const removeProject = vi.fn()
    const setCurrentProject = vi.fn()
    const dialogService = createDialogService()
    const actions = useSidebarProjectActions({
      busy: false,
      currentProject: createProject('project-a'),
      addProject: vi.fn(),
      removeProject,
      setCurrentProject,
      setProjectExpanded: vi.fn(),
      setShowProjectModal: vi.fn(),
      setFormData: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleDeleteProject(createProject('project-a'))

    expect(dialogService.confirmAction).toHaveBeenCalledWith('确定删除项目“project-a”吗？项目下的聊天也会一并移除。')
    expect(deleteProjectApiMock).toHaveBeenCalledWith('project-a')
    expect(removeProject).toHaveBeenCalledWith('project-a')
    expect(setCurrentProject).toHaveBeenCalledWith(null)
  })

  it('reports project action failures through the dialog service', async () => {
    createProjectApiMock.mockRejectedValue(new Error('boom'))
    const dialogService = createDialogService()
    const actions = useSidebarProjectActions({
      busy: false,
      currentProject: null,
      addProject: vi.fn(),
      removeProject: vi.fn(),
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setShowProjectModal: vi.fn(),
      setFormData: vi.fn(),
      navigate: vi.fn(),
      dialogService,
    })

    await actions.handleCreateProject({ name: 'Demo', path: '/tmp/demo', language: 'typescript' })

    expect(dialogService.notifyError).toHaveBeenCalledWith('创建项目失败')
  })

  it('does not open directory selection while busy', async () => {
    const actions = useSidebarProjectActions({
      busy: true,
      currentProject: null,
      addProject: vi.fn(),
      removeProject: vi.fn(),
      setCurrentProject: vi.fn(),
      setProjectExpanded: vi.fn(),
      setShowProjectModal: vi.fn(),
      setFormData: vi.fn(),
      navigate: vi.fn(),
    })

    await actions.handleSelectDirectory()

    expect(selectProjectDirectoryMock).not.toHaveBeenCalled()
  })
})
