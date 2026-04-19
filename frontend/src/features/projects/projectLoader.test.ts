import { describe, expect, it, vi } from 'vitest'
import type { Project } from '@/types/project'
import { createProjectLoader } from './projectLoader'

interface ProjectLoaderState {
  loaded: boolean
  loading: boolean
  projects: Project[]
}

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

describe('createProjectLoader', () => {
  it('deduplicates concurrent loads and updates the store once', async () => {
    const state: ProjectLoaderState = {
      loaded: false,
      loading: false,
      projects: [],
    }
    const listProjects = vi.fn(async () => [createProject('project-a')])
    const loader = createProjectLoader({
      isDemoMode: () => false,
      getDemoProjects: () => [],
      listProjects,
      getState: () => state,
      setLoading: (loading) => {
        state.loading = loading
      },
      setProjects: (projects) => {
        state.projects = projects
        state.loaded = true
      },
    })

    await Promise.all([loader(), loader()])

    expect(listProjects).toHaveBeenCalledTimes(1)
    expect(state.projects.map((project) => project.id)).toEqual(['project-a'])
    expect(state.loading).toBe(false)
  })

  it('skips the network request when projects are already loaded', async () => {
    const state: ProjectLoaderState = {
      loaded: true,
      loading: false,
      projects: [createProject('project-a')],
    }
    const listProjects = vi.fn(async () => [createProject('project-b')])
    const loader = createProjectLoader({
      isDemoMode: () => false,
      getDemoProjects: () => [],
      listProjects,
      getState: () => state,
      setLoading: () => undefined,
      setProjects: () => undefined,
    })

    const projects = await loader()

    expect(listProjects).not.toHaveBeenCalled()
    expect(projects.map((project) => project.id)).toEqual(['project-a'])
  })
})
