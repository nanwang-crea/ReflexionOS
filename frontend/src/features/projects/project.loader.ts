/**
 * 文件功能：项目列表加载器
 * 文件描述：确保项目列表被加载到 project.store，并在加载完成后预加载每个项目的会话（sessions）。
 * 通过工厂函数 createProjectLoader 生成加载器，便于单元测试注入 mock 依赖。
 * 核心逻辑：使用模块级 inFlight Promise 做请求去重——并发调用 ensureProjectsLoaded 时只会
 * 真正发起一次网络请求，其余调用等待同一个 Promise；已加载过（loaded=true）且非强制刷新时直接跳过请求。
 */

import { ensureProjectSessionsLoaded } from '@/features/sessions/session.actions'
import { projectApi } from './api/project.api'
import { useProjectStore } from '@/features/projects/stores/project.store'
import type { Project } from '@/types/project'

/** 项目加载器所需读取的 store 状态子集：是否已加载、当前项目列表 */
interface ProjectLoaderStoreState {
  loaded: boolean
  projects: Project[]
}

/** 创建项目加载器所需的依赖项：项目列表请求函数、状态读取/写入函数（便于测试时替换为 mock） */
interface CreateProjectLoaderOptions {
  listProjects: () => Promise<Project[]>
  getState: () => ProjectLoaderStoreState
  setLoading: (loading: boolean) => void
  setProjects: (projects: Project[]) => void
}

/**
 * 函数名：createProjectLoader
 * 入参：
 *   - options (CreateProjectLoaderOptions): 加载器依赖项，包含请求函数与状态读写函数
 * 功能：生成一个带请求去重能力的 ensureProjectsLoaded 函数
 * 运行逻辑：
 *   1. 若非强制刷新且 store 已标记为 loaded，直接返回当前项目列表，不发起请求
 *   2. 若已有一个加载请求在途（inFlight 非空），直接复用该 Promise，避免重复请求
 *   3. 否则发起新请求：设置 loading，拉取项目列表并写入 store，
 *      再并发为每个项目预加载会话数据，最终清理 loading 与 inFlight 标记
 * 出参：函数 ensureProjectsLoaded({ force?: boolean }) => Promise<Project[]>
 */
function createProjectLoader(options: CreateProjectLoaderOptions) {
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
        const projects = await options.listProjects()

        options.setProjects(projects)

        await Promise.all(projects.map((project) => ensureProjectSessionsLoaded(project.id)))

        return projects
      } finally {
        options.setLoading(false)
        inFlight = null
      }
    })()

    return inFlight
  }
}

// 使用真实的 projectApi 和 project.store 创建默认加载器实例（生产环境使用）
const ensureProjectsLoadedInternal = createProjectLoader({
  listProjects: async () => {
    const response = await projectApi.list()
    return response.data
  },
  getState: () => useProjectStore.getState(),
  setLoading: (loading) => useProjectStore.getState().setLoading(loading),
  setProjects: (projects) => useProjectStore.getState().setProjects(projects),
})

/**
 * 函数名：ensureProjectsLoaded
 * 入参：
 *   - options ({ force?: boolean } 可选): force 为 true 时强制重新拉取，忽略已加载状态
 * 功能：对外暴露的项目加载入口，供页面/组件调用以确保项目列表已就位
 * 运行逻辑：委托给内部加载器实例 ensureProjectsLoadedInternal 执行
 * 出参：Promise<Project[]> - 加载完成后的项目列表
 */
export function ensureProjectsLoaded(options?: { force?: boolean }) {
  return ensureProjectsLoadedInternal(options)
}
