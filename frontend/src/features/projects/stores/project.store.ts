/**
 * 文件功能：项目 Zustand Store
 * 文件描述：管理项目列表、当前选中项目、加载状态；currentProject 持久化到 localStorage，
 * 以便应用重启后自动恢复上次选中的项目。
 * 核心逻辑：setProjects/addProject/removeProject 均会将 loaded 置为 true，
 * 表示项目数据已经被写入过 store；removeProject 和 setProjects 会同步校正 currentProject
 * （若当前项目被移除或不在新列表中，则清空 currentProject）。
 */

import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { Project } from '@/types/project'

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  loading: boolean
  loaded: boolean
  setProjects: (projects: Project[]) => void
  addProject: (project: Project) => void
  removeProject: (id: string) => void
  setCurrentProject: (project: Project | null) => void
  setLoading: (loading: boolean) => void
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      projects: [],
      currentProject: null,
      loading: false,
      loaded: false,

      /**
       * 整体替换项目列表（通常在从后端拉取全量项目后调用）。
       * 入参：projects（新的项目数组）
       * 运行逻辑：标记 loaded=true；若已有 currentProject，则在新列表中重新查找同 id 项目
       * 保持引用最新，若找不到（如项目已被删除）则清空 currentProject。
       */
      setProjects: (projects) => set((state) => ({
        projects,
        loaded: true,
        currentProject: state.currentProject
          ? projects.find((project) => project.id === state.currentProject?.id) || null
          : null
      })),

      /** 追加新建的项目到列表末尾，并标记 loaded=true。入参：project（新建的项目对象） */
      addProject: (project) => set((state) => ({
        loaded: true,
        projects: [...state.projects, project]
      })),

      /**
       * 按 id 移除项目。入参：id（项目 id）
       * 运行逻辑：从列表过滤掉该项目；若被删除的正是当前选中项目，则将 currentProject 置空。
       */
      removeProject: (id) => set((state) => ({
        loaded: true,
        projects: state.projects.filter((project) => project.id !== id),
        currentProject: state.currentProject?.id === id ? null : state.currentProject
      })),

      /** 设置当前选中的项目。入参：project（目标项目，或 null 表示取消选中） */
      setCurrentProject: (project) => set({ currentProject: project }),

      /** 设置加载中状态。入参：loading（是否正在加载项目列表） */
      setLoading: (loading) => set({ loading }),
    }),
    {
      name: 'reflexion-project',
      storage: createJSONStorage(() => localStorage),
      // 只持久化 currentProject，避免刷新后项目列表数据过期
      partialize: (state) => ({
        currentProject: state.currentProject
      })
    }
  )
)
