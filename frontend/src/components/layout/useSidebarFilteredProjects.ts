// 提供 sidebar 项目/会话搜索过滤逻辑：按搜索关键字过滤项目和会话列表，并对会话按更新时间排序。
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

// 参数：projects - 全部项目列表；projectSessionsById - 按项目 id 索引的会话列表；searchQuery - 搜索关键字。
// 作用：将每个项目下的会话按更新时间倒序排列；若无搜索词，直接返回全部项目及其会话；
// 若有搜索词，则匹配项目名称（命中则该项目下全部会话都保留）或会话标题（仅保留命中的会话），
// 项目名和会话标题都未命中的项目会被整体过滤掉。
// 返回：过滤后的项目及其对应会话列表数组。
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

// 参数：options - 同 getFilteredProjects，包含 projects/projectSessionsById/searchQuery。
// 作用：对 getFilteredProjects 的结果做 useMemo 缓存，避免每次渲染重复计算过滤逻辑。
// 返回：缓存后的过滤项目列表（SidebarFilteredProject[]）。
export function useSidebarFilteredProjects(options: GetFilteredProjectsOptions) {
  const { projects, projectSessionsById, searchQuery } = options

  return useMemo(
    () => getFilteredProjects({ projects, projectSessionsById, searchQuery }),
    [projectSessionsById, projects, searchQuery]
  )
}
