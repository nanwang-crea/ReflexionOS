import { beforeEach, describe, expect, it, vi } from 'vitest'
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

const listProjectsMock = vi.fn()

vi.mock('@/demo/demoData', () => ({
  isDemoMode: () => false,
  demoProjects: [],
}))

vi.mock('@/services/apiClient', () => ({
  projectApi: {
    list: listProjectsMock,
  },
}))

beforeEach(() => {
  vi.resetModules()
  listProjectsMock.mockReset()
})

describe('ensureProjectsLoaded', () => {
  it('deduplicates concurrent loads and updates the store once', async () => {
    listProjectsMock.mockResolvedValue({
      data: [createProject('project-a')],
    })

    const { useProjectStore } = await import('@/stores/projectStore')
    useProjectStore.setState({
      loaded: false,
      loading: false,
      projects: [],
      currentProject: null,
    })

    const { ensureProjectsLoaded } = await import('./projectLoader')

    await Promise.all([ensureProjectsLoaded(), ensureProjectsLoaded()])

    expect(listProjectsMock).toHaveBeenCalledTimes(1)
    expect(useProjectStore.getState().projects.map((project) => project.id)).toEqual(['project-a'])
    expect(useProjectStore.getState().loading).toBe(false)
  })

  it('skips the network request when projects are already loaded', async () => {
    const { useProjectStore } = await import('@/stores/projectStore')
    useProjectStore.setState({
      loaded: true,
      loading: false,
      projects: [createProject('project-a')],
      currentProject: null,
    })

    const { ensureProjectsLoaded } = await import('./projectLoader')
    const projects = await ensureProjectsLoaded()

    expect(listProjectsMock).not.toHaveBeenCalled()
    expect(projects.map((project) => project.id)).toEqual(['project-a'])
  })
})
