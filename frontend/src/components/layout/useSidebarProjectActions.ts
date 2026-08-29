// sidebar 项目相关操作的 hook：封装创建项目、删除项目、选择项目本地目录三个异步操作，
// 统一处理成功后的状态更新与失败后的错误提示（toast/dialog），供 WorkspaceSidebar 使用。
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

// 参数：formData - 新建项目的表单数据（名称、路径）；addProject/setCurrentProject/setProjectExpanded/
// setShowProjectModal/setFormData/navigate - 各类状态更新与导航回调。
// 作用：校验项目名称非空后调用后端创建项目，成功后将新项目加入 store、设为当前项目并展开，
// 关闭新建弹窗、重置表单，并导航到 /agent 页面。
// 返回：Promise<void>；名称为空时抛出 Error。
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

// 参数：project - 待删除的项目；currentProject - 当前选中的项目；removeProject/setCurrentProject - 状态更新回调。
// 作用：调用后端删除项目，成功后从 store 移除；若被删除的项目正是当前选中项目，则清空当前项目选择。
// 返回：Promise<void>。
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

// 参数：setFormData - 表单数据更新函数。
// 作用：调起系统目录选择对话框（仅 Electron 环境可用），选中目录后取目录名作为默认项目名，
// 并将路径和名称写回表单；用户取消选择时不做任何更新。
// 返回：Promise<void>。
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

// 参数：busy - 当前会话是否忙碌（忙碌时阻止删除/选择目录等操作）；currentProject/addProject/removeProject/
// setCurrentProject/setProjectExpanded/setShowProjectModal/setFormData/navigate - 状态与导航依赖；
// dialogService - 弹框服务（默认使用 nativeDialogService，测试时可替换）。
// 作用：把创建/删除项目、选择目录三个底层操作包装成带错误处理（toast 提示）和 busy 判断的事件处理函数，
// 删除项目前会通过 dialogService 弹出二次确认。
// 返回：{ handleCreateProject, handleDeleteProject, handleSelectDirectory } 三个可直接绑定到 UI 事件的函数。
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

    const confirmed = await dialogService.confirmAction(`确定删除项目”${project.name}”吗？项目下的聊天也会一并移除。`, { variant: 'danger' })
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
