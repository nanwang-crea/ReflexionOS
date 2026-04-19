import { demoProjects, isDemoMode } from '@/demo/demoData'
import { projectApi } from '@/services/apiClient'
import { useProjectStore } from '@/stores/projectStore'
import type { Project } from '@/types/project'

interface ProjectLoaderStoreState {
  loaded: boolean
  projects: Project[]
}

interface CreateProjectLoaderOptions {
  isDemoMode: () => boolean
  getDemoProjects: () => Project[]
  listProjects: () => Promise<Project[]>
  getState: () => ProjectLoaderStoreState
  setLoading: (loading: boolean) => void
  setProjects: (projects: Project[]) => void
}

export function createProjectLoader(options: CreateProjectLoaderOptions) {
  let inFlight: Promise<Project[]> | null = null

  return async function ensureProjectsLoaded({ force = false }: { force?: boolean } = {}) {
    const state = options.getState()
    if (!force && state.loaded) {
      return state.projects
    }

    if (inFlight) {
      return inFlight
    }

    inFlight = (async () => {
      options.setLoading(true)

      try {
        const projects = options.isDemoMode()
          ? options.getDemoProjects()
          : await options.listProjects()

        options.setProjects(projects)
        return projects
      } finally {
        options.setLoading(false)
        inFlight = null
      }
    })()

    return inFlight
  }
}

const ensureProjectsLoadedInternal = createProjectLoader({
  isDemoMode,
  getDemoProjects: () => demoProjects,
  listProjects: async () => {
    const response = await projectApi.list()
    return response.data
  },
  getState: () => useProjectStore.getState(),
  setLoading: (loading) => useProjectStore.getState().setLoading(loading),
  setProjects: (projects) => useProjectStore.getState().setProjects(projects),
})

export function ensureProjectsLoaded(options?: { force?: boolean }) {
  return ensureProjectsLoadedInternal(options)
}
