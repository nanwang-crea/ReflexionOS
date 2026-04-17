import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { Project } from '@/types/project'

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  loading: boolean
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
      
      setProjects: (projects) => set((state) => ({
        projects,
        currentProject: state.currentProject
          ? projects.find((project) => project.id === state.currentProject?.id) || null
          : null
      })),
      
      addProject: (project) => set((state) => ({
        projects: [...state.projects, project]
      })),
      
      removeProject: (id) => set((state) => ({
        projects: state.projects.filter((project) => project.id !== id),
        currentProject: state.currentProject?.id === id ? null : state.currentProject
      })),
      
      setCurrentProject: (project) => set({ currentProject: project }),
      
      setLoading: (loading) => set({ loading }),
    }),
    {
      name: 'reflexion-project',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        currentProject: state.currentProject
      })
    }
  )
)
