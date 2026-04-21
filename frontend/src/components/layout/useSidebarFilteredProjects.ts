import { useMemo } from 'react'
import type { Project } from '@/types/project'
import type { SessionSummary } from '@/types/workspace'

export interface SidebarFilteredProject {
  project: Project
  sessions: SessionSummary[]
}

interface GetFilteredProjectsOptions {
  projects: Project[]
  projectSessionsById: Record<string, SessionSummary[]>
  searchQuery: string
}

export function getFilteredProjects({
  projects,
  projectSessionsById,
  searchQuery,
}: GetFilteredProjectsOptions): SidebarFilteredProject[] {
  const normalizedQuery = searchQuery.trim().toLowerCase()

  return projects
    .map((project) => {
      const projectSessions = [...(projectSessionsById[project.id] || [])].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      )

      if (!normalizedQuery) {
        return { project, sessions: projectSessions }
      }

      const matchesProject = project.name.toLowerCase().includes(normalizedQuery)
      const matchedSessions = projectSessions.filter((session) =>
        session.title.toLowerCase().includes(normalizedQuery)
      )

      if (!matchesProject && matchedSessions.length === 0) {
        return null
      }

      return {
        project,
        sessions: matchesProject ? projectSessions : matchedSessions,
      }
    })
    .filter((entry): entry is SidebarFilteredProject => entry !== null)
}

export function useSidebarFilteredProjects(options: GetFilteredProjectsOptions) {
  const { projects, projectSessionsById, searchQuery } = options

  return useMemo(
    () => getFilteredProjects({ projects, projectSessionsById, searchQuery }),
    [projectSessionsById, projects, searchQuery]
  )
}
