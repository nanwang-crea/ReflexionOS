/**
 * project.loader 单元测试：覆盖并发加载去重、已加载时跳过网络请求、
 * 加载后为每个项目预加载会话（session）等核心行为。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Project } from '@/types/project'

/** 构造测试用的 Project 对象。入参：id（项目 id，同时用作 name）。出参：Project 对象 */
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
const ensureProjectSessionsLoadedMock = vi.fn()

vi.mock('../api/project.api', () => ({
  projectApi: {
    list: listProjectsMock,
  },
}))

vi.mock('@/features/sessions/session.actions', () => ({
  ensureProjectSessionsLoaded: ensureProjectSessionsLoadedMock,
}))

beforeEach(() => {
  vi.resetModules()
  listProjectsMock.mockReset()
  ensureProjectSessionsLoadedMock.mockReset()
  ensureProjectSessionsLoadedMock.mockResolvedValue(undefined)
})

describe('ensureProjectsLoaded', () => {
  it('deduplicates concurrent loads and updates the store once', async () => {
    listProjectsMock.mockResolvedValue({
      data: [createProject('project-a')],
    })

    const { useProjectStore } = await import('@/features/projects/stores/project.store')
    useProjectStore.setState({
      loaded: false,
      loading: false,
      projects: [],
      currentProject: null,
    })

    const { ensureProjectsLoaded } = await import('../project.loader')

    await Promise.all([ensureProjectsLoaded(), ensureProjectsLoaded()])

    expect(listProjectsMock).toHaveBeenCalledTimes(1)
    expect(useProjectStore.getState().projects.map((project) => project.id)).toEqual(['project-a'])
    expect(useProjectStore.getState().loading).toBe(false)
  })

  it('skips the network request when projects are already loaded', async () => {
    const { useProjectStore } = await import('@/features/projects/stores/project.store')
    useProjectStore.setState({
      loaded: true,
      loading: false,
      projects: [createProject('project-a')],
      currentProject: null,
    })

    const { ensureProjectsLoaded } = await import('../project.loader')
    const projects = await ensureProjectsLoaded()

    expect(listProjectsMock).not.toHaveBeenCalled()
    expect(projects.map((project) => project.id)).toEqual(['project-a'])
  })

  it('calls ensureProjectSessionsLoaded for each loaded project', async () => {
    listProjectsMock.mockResolvedValue({
      data: [createProject('project-a'), createProject('project-b')],
    })

    const { useProjectStore } = await import('@/features/projects/stores/project.store')
    useProjectStore.setState({
      loaded: false,
      loading: false,
      projects: [],
      currentProject: null,
    })

    const { ensureProjectsLoaded } = await import('../project.loader')
    await ensureProjectsLoaded({ force: true })

    expect(ensureProjectSessionsLoadedMock).toHaveBeenCalledTimes(2)
    expect(ensureProjectSessionsLoadedMock).toHaveBeenNthCalledWith(1, 'project-a')
    expect(ensureProjectSessionsLoadedMock).toHaveBeenNthCalledWith(2, 'project-b')
  })

  it('preloads project sessions during project loading', async () => {
    listProjectsMock.mockResolvedValue({
      data: [createProject('project-1')],
    })

    const { useProjectStore } = await import('@/features/projects/stores/project.store')
    useProjectStore.setState({
      loaded: false,
      loading: false,
      projects: [],
      currentProject: null,
    })

    const { ensureProjectsLoaded } = await import('../project.loader')
    await ensureProjectsLoaded({ force: true })

    expect(ensureProjectSessionsLoadedMock).toHaveBeenCalledWith('project-1')
  })

})
