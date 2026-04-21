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
const listProjectSessionsMock = vi.fn()

vi.mock('@/demo/demoData', () => ({
  isDemoMode: () => false,
  demoProjects: [],
}))

vi.mock('@/services/apiClient', () => ({
  projectApi: {
    list: listProjectsMock,
  },
}))

vi.mock('@/features/sessions/sessionApi', () => ({
  sessionApi: {
    listProjectSessions: listProjectSessionsMock,
  },
}))

beforeEach(() => {
  vi.resetModules()
  listProjectsMock.mockReset()
  listProjectSessionsMock.mockReset()
  listProjectSessionsMock.mockResolvedValue({ data: [] })
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

  it('hydrates sessionStore for each loaded project', async () => {
    listProjectsMock.mockResolvedValue({
      data: [createProject('project-a'), createProject('project-b')],
    })
    listProjectSessionsMock
      .mockResolvedValueOnce({
        data: [{
          id: 'session-a',
          projectId: 'project-a',
          title: 'Project A Chat',
          createdAt: '2026-04-20T00:00:00Z',
          updatedAt: '2026-04-20T00:00:00Z',
        }],
      })
      .mockResolvedValueOnce({
        data: [{
          id: 'session-b',
          projectId: 'project-b',
          title: 'Project B Chat',
          createdAt: '2026-04-20T00:01:00Z',
          updatedAt: '2026-04-20T00:01:00Z',
        }],
      })

    const { useProjectStore } = await import('@/stores/projectStore')
    const { useSessionStore } = await import('@/features/sessions/sessionStore')
    useProjectStore.setState({
      loaded: false,
      loading: false,
      projects: [],
      currentProject: null,
    })
    useSessionStore.setState({
      sessionsByProjectId: {},
      historyBySessionId: {},
    })

    const { ensureProjectsLoaded } = await import('./projectLoader')
    await ensureProjectsLoaded({ force: true })

    expect(listProjectSessionsMock).toHaveBeenCalledTimes(2)
    expect(listProjectSessionsMock).toHaveBeenNthCalledWith(1, 'project-a')
    expect(listProjectSessionsMock).toHaveBeenNthCalledWith(2, 'project-b')
    expect(useSessionStore.getState().sessionsByProjectId).toEqual({
      'project-a': [{
        id: 'session-a',
        projectId: 'project-a',
        title: 'Project A Chat',
        createdAt: '2026-04-20T00:00:00Z',
        updatedAt: '2026-04-20T00:00:00Z',
      }],
      'project-b': [{
        id: 'session-b',
        projectId: 'project-b',
        title: 'Project B Chat',
        createdAt: '2026-04-20T00:01:00Z',
        updatedAt: '2026-04-20T00:01:00Z',
      }],
    })
  })

  it('preloads project sessions during project loading', async () => {
    listProjectsMock.mockResolvedValue({
      data: [createProject('project-1')],
    })

    const { useProjectStore } = await import('@/stores/projectStore')
    useProjectStore.setState({
      loaded: false,
      loading: false,
      projects: [],
      currentProject: null,
    })

    const { ensureProjectsLoaded } = await import('./projectLoader')
    await ensureProjectsLoaded({ force: true })

    expect(listProjectSessionsMock).toHaveBeenCalledWith('project-1')
  })

})
