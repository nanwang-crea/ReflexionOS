import { describe, expect, it } from 'vitest'
import { getFilteredProjects } from './useSidebarFilteredProjects'
import type { Project } from '@/types/project'
import type { SessionSummary } from '@/types/workspace'

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

function createSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: 'session-1',
    projectId: 'project-a',
    title: 'Session',
    createdAt: '2026-04-20T00:00:00Z',
    updatedAt: '2026-04-20T00:00:00Z',
    ...overrides,
  }
}

describe('getFilteredProjects', () => {
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
