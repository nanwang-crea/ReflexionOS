// getFilteredProjects 的单测：验证侧边栏项目/会话列表按 updatedAt 排序、
// 以及按搜索关键字过滤项目名/会话标题的行为。
import { describe, expect, it } from 'vitest'
import { getFilteredProjects } from '../useSidebarFilteredProjects'
import type { Project } from '@/types/project'
import type { SessionSummary } from '@/types/workspace'

// 参数：id - 项目 id；name - 项目名称（默认等于 id）。
// 作用：构造一个最小 Project 测试夹具。
// 返回：完整的 Project 对象。
function createProject(id: string, name = id): Project {
  return {
    id,
    name,
    path: `/tmp/${id}`,
    language: 'typescript',
    created_at: '2026-04-19T00:00:00.000Z',
    updated_at: '2026-04-19T00:00:00.000Z',
  }
}

// 参数：overrides - 需要覆盖的 SessionSummary 字段。
// 作用：构造一个带默认值的最小 SessionSummary 测试夹具。
// 返回：完整的 SessionSummary 对象。
function createSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: 'session-1',
    projectId: 'project-a',
    title: 'Session',
    agentMode: 'build',
    lastEventSeq: 0,
    activeTurnId: null,
    createdAt: '2026-04-20T00:00:00Z',
    updatedAt: '2026-04-20T00:00:00Z',
    ...overrides,
  }
}

describe('getFilteredProjects', () => {
  // 参数：无。
  // 验证：不带搜索词时，同一项目下的会话按 updatedAt 倒序排列（最新的排最前）。
  it('filters and sorts project sessions by updatedAt descending', () => {
    const result = getFilteredProjects({
      projects: [createProject('project-a')],
      projectSessionsById: {
        'project-a': [
          createSession({
            id: 'session-older',
            title: 'Older Session',
            updatedAt: '2026-04-20T01:00:00Z',
          }),
          createSession({
            id: 'session-newer',
            title: 'Newest Session',
            updatedAt: '2026-04-20T02:00:00Z',
          }),
        ],
      },
      searchQuery: '',
    })

    expect(result).toHaveLength(1)
    expect(result[0]?.sessions.map((session) => session.id)).toEqual([
      'session-newer',
      'session-older',
    ])
  })

  // 参数：无。
  // 验证：搜索词匹配项目名称时，该项目下的所有会话都保留（不再按标题过滤会话）。
  it('keeps all project sessions when the project name matches the search query', () => {
    const result = getFilteredProjects({
      projects: [createProject('project-a', 'Alpha Workspace'), createProject('project-b', 'Beta Workspace')],
      projectSessionsById: {
        'project-a': [
          createSession({ id: 'session-a1', projectId: 'project-a', title: 'First Chat' }),
          createSession({ id: 'session-a2', projectId: 'project-a', title: 'Second Chat' }),
        ],
        'project-b': [
          createSession({ id: 'session-b1', projectId: 'project-b', title: 'Other Chat' }),
        ],
      },
      searchQuery: 'alpha',
    })

    expect(result).toHaveLength(1)
    expect(result[0]?.project.id).toBe('project-a')
    expect(result[0]?.sessions.map((session) => session.id)).toEqual(['session-a1', 'session-a2'])
  })

  // 参数：无。
  // 验证：搜索词不匹配项目名称、但匹配某个会话标题时，只保留标题匹配的会话。
  it('keeps only matching sessions when the session title matches the search query', () => {
    const result = getFilteredProjects({
      projects: [createProject('project-a', 'Alpha Workspace')],
      projectSessionsById: {
        'project-a': [
          createSession({ id: 'session-a1', projectId: 'project-a', title: 'Bugfix Chat' }),
          createSession({ id: 'session-a2', projectId: 'project-a', title: 'Planning Notes' }),
        ],
      },
      searchQuery: 'plan',
    })

    expect(result).toHaveLength(1)
    expect(result[0]?.sessions.map((session) => session.id)).toEqual(['session-a2'])
  })

  // 参数：无。
  // 验证：搜索词既不匹配任何项目名称也不匹配任何会话标题时，结果为空数组（项目被整体移除）。
  it('removes projects with no project-name or session-title match', () => {
    const result = getFilteredProjects({
      projects: [createProject('project-a', 'Alpha Workspace'), createProject('project-b', 'Beta Workspace')],
      projectSessionsById: {
        'project-a': [
          createSession({ id: 'session-a1', projectId: 'project-a', title: 'Bugfix Chat' }),
        ],
        'project-b': [
          createSession({ id: 'session-b1', projectId: 'project-b', title: 'Planning Notes' }),
        ],
      },
      searchQuery: 'gamma',
    })

    expect(result).toEqual([])
  })
})
