import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSidebarProject, deleteSidebarProject, selectSidebarProjectDirectory } from './useSidebarProjectActions'
import { useSidebarProjectActions } from './useSidebarProjectActions'
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

describe('useSidebarProjectActions helpers', () => {
  beforeEach(() => {
    createProjectApiMock.mockReset()
    deleteProjectApiMock.mockReset()
    selectProjectDirectoryMock.mockReset()
  })

  it('creates a project and resets the form state', async () => {
    createProjectApiMock.mockResolvedValue({
      data: createProject('project-created'),
    })

    const addProject = vi.fn()
    const setCurrentProject = vi.fn()
    const setProjectExpanded = vi.fn()
    const setShowProjectModal = vi.fn()
    const setFormData = vi.fn()
    const navigate = vi.fn()

    await createSidebarProject({
      formData: { name: 'Created', path: '/tmp/created', language: 'typescript' },
      addProject,
      setCurrentProject,
      setProjectExpanded,
      setShowProjectModal,
      setFormData,
      navigate,
    })

    expect(createProjectApiMock).toHaveBeenCalledWith({
      name: 'Created',
      path: '/tmp/created',
      language: 'typescript',
    })
    expect(addProject).toHaveBeenCalledWith(createProject('project-created'))
    expect(setCurrentProject).toHaveBeenCalledWith(createProject('project-created'))
    expect(setProjectExpanded).toHaveBeenCalledWith('project-created', true)
    expect(setShowProjectModal).toHaveBeenCalledWith(false)
    expect(setFormData).toHaveBeenCalledWith({ name: '', path: '', language: 'python' })
    expect(navigate).toHaveBeenCalledWith('/agent')
  })

  it('deletes a project and clears current selection when needed', async () => {
    deleteProjectApiMock.mockResolvedValue(undefined)
    const removeProject = vi.fn()
    const setCurrentProject = vi.fn()

    await deleteSidebarProject({
      project: createProject('project-a'),
      currentProject: createProject('project-a'),
      removeProject,
      setCurrentProject,
    })

    expect(deleteProjectApiMock).toHaveBeenCalledWith('project-a')
    expect(removeProject).toHaveBeenCalledWith('project-a')
    expect(setCurrentProject).toHaveBeenCalledWith(null)
  })

  it('selects a project directory and updates the form path', async () => {
    selectProjectDirectoryMock.mockResolvedValue('/tmp/selected')
    const setFormData = vi.fn()

    await selectSidebarProjectDirectory({ setFormData })

    expect(selectProjectDirectoryMock).toHaveBeenCalledTimes(1)
    expect(setFormData).toHaveBeenCalledWith(expect.any(Function))

    const update = setFormData.mock.calls[0]?.[0]
    expect(update({ name: 'Demo', path: '', language: 'python' })).toEqual({
      name: 'Demo',
      path: '/tmp/selected',
      language: 'python',
    })
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
