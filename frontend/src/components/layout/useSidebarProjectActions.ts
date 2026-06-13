import type { Dispatch, SetStateAction } from 'react'
import { projectApi } from '@/features/projects/api/project.api'
import { nativeDialogService, type DialogService } from '@/services/dialogService'
import { selectProjectDirectory } from '@/services/desktopClient'
import type { Project } from '@/types/project'

interface ProjectFormData {
  name: string
  path: string
}

export type SidebarProjectFormData = ProjectFormData

interface CreateSidebarProjectOptions {
  formData: ProjectFormData
  addProject: (project: Project) => void
  setCurrentProject: (project: Project | null) => void
  setProjectExpanded: (projectId: string, expanded: boolean) => void
  setShowProjectModal: (open: boolean) => void
  setFormData: Dispatch<SetStateAction<ProjectFormData>> | ((formData: ProjectFormData) => void)
  navigate: (to: string) => void
}

interface DeleteSidebarProjectOptions {
  project: Project
  currentProject: Project | null
  removeProject: (projectId: string) => void
  setCurrentProject: (project: Project | null) => void
}

interface SelectSidebarProjectDirectoryOptions {
  setFormData: Dispatch<SetStateAction<ProjectFormData>>
}

async function createSidebarProject({
  formData,
  addProject,
  setCurrentProject,
  setProjectExpanded,
  setShowProjectModal,
  setFormData,
  navigate,
}: CreateSidebarProjectOptions) {
  if (!formData.name.trim()) {
    throw new Error('项目名称不能为空')
  }

  const response = await projectApi.create({ name: formData.name.trim(), path: formData.path })
  addProject(response.data)
  setCurrentProject(response.data)
  setProjectExpanded(response.data.id, true)
  setShowProjectModal(false)
  setFormData({ name: '', path: '' })
  navigate('/agent')
}

async function deleteSidebarProject({
  project,
  currentProject,
  removeProject,
  setCurrentProject,
}: DeleteSidebarProjectOptions) {
  await projectApi.delete(project.id)
  removeProject(project.id)
  if (currentProject?.id === project.id) {
    setCurrentProject(null)
  }
}

async function selectSidebarProjectDirectory({
  setFormData,
}: SelectSidebarProjectDirectoryOptions) {
  const selectedPath = await selectProjectDirectory()

  if (!selectedPath) {
    return
  }

  const dirName = selectedPath.split(/[\\/]/).pop() || ''
  setFormData((current) => ({ ...current, path: selectedPath, name: dirName }))
}

interface UseSidebarProjectActionsOptions {
  busy: boolean
  currentProject: Project | null
  addProject: (project: Project) => void
  removeProject: (projectId: string) => void
  setCurrentProject: (project: Project | null) => void
  setProjectExpanded: (projectId: string, expanded: boolean) => void
  setShowProjectModal: (open: boolean) => void
  setFormData: Dispatch<SetStateAction<ProjectFormData>>
  navigate: (to: string) => void
  dialogService?: DialogService
}

export function useSidebarProjectActions({
  busy,
  currentProject,
  addProject,
  removeProject,
  setCurrentProject,
  setProjectExpanded,
  setShowProjectModal,
  setFormData,
  navigate,
  dialogService = nativeDialogService,
}: UseSidebarProjectActionsOptions) {
  const handleCreateProject = async (formData: ProjectFormData) => {
    try {
      await createSidebarProject({
        formData,
        addProject,
        setCurrentProject,
        setProjectExpanded,
        setShowProjectModal,
        setFormData,
        navigate,
      })
    } catch (error) {
      console.error('Failed to create project:', error)
      const message = error instanceof Error ? error.message : '创建项目失败'
      dialogService.notifyError(message)
    }
  }

  const handleDeleteProject = async (project: Project) => {
    if (busy) {
      return
    }

    const confirmed = dialogService.confirmAction(`确定删除项目“${project.name}”吗？项目下的聊天也会一并移除。`)
    if (!confirmed) {
      return
    }

    try {
      await deleteSidebarProject({
        project,
        currentProject,
        removeProject,
        setCurrentProject,
      })
    } catch (error) {
      console.error('Failed to delete project:', error)
      dialogService.notifyError('删除项目失败')
    }
  }

  const handleSelectDirectory = async () => {
    if (busy) {
      return
    }

    await selectSidebarProjectDirectory({ setFormData })
  }

  return {
    handleCreateProject,
    handleDeleteProject,
    handleSelectDirectory,
  }
}
