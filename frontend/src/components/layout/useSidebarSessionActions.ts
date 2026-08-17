// sidebar 会话相关操作的 hook：封装新建会话、重命名会话、删除会话三个异步操作，
// 统一处理成功后的状态更新与失败后的错误提示（toast/dialog），供 WorkspaceSidebar 使用。
import { createSession, deleteSession, renameSession } from '@/features/sessions/session.actions'
import { nativeDialogService, type DialogService } from '@/services/dialogService'
import type { Project } from '@/types/project'
import type { SessionSummary } from '@/types/workspace'

interface CreateSidebarSessionOptions {
  projectId: string
  defaultProviderId?: string | null
  defaultModelId?: string | null
}

interface DeleteSidebarSessionOptions {
  session: SessionSummary
  currentSessionId: string | null
  setCurrentSessionId: (sessionId: string | null) => void
}

// 参数：projectId - 会话所属项目 id；defaultProviderId/defaultModelId - 用户在设置中配置的默认供应商/模型，
// 作为新会话的首选项传入。
// 作用：调用底层 createSession 在指定项目下创建新会话。
// 返回：Promise，resolve 为新建的会话对象。
async function createSidebarSession({
  projectId,
  defaultProviderId,
  defaultModelId,
}: CreateSidebarSessionOptions) {
  return createSession(projectId, {
    preferredProviderId: defaultProviderId,
    preferredModelId: defaultModelId,
  })
}

// 参数：session - 待删除的会话；currentSessionId - 当前选中的会话 id；setCurrentSessionId - 状态更新回调。
// 作用：调用后端删除该会话；若被删除的会话正是当前选中会话，则清空当前会话选择。
// 返回：Promise<void>。
async function deleteSidebarSession({
  session,
  currentSessionId,
  setCurrentSessionId,
}: DeleteSidebarSessionOptions) {
  await deleteSession(session.projectId, session.id)
  if (currentSessionId === session.id) {
    setCurrentSessionId(null)
  }
}

interface UseSidebarSessionActionsOptions {
  busy: boolean
  projects: Project[]
  currentProject: Project | null
  currentSessionId: string | null
  defaultProviderId?: string | null
  defaultModelId?: string | null
  setCurrentProject: (project: Project | null) => void
  setProjectExpanded: (projectId: string, expanded: boolean) => void
  setCurrentSessionId: (sessionId: string | null) => void
  setShowProjectModal: (open: boolean) => void
  navigate: (to: string) => void
  dialogService?: DialogService
}

// 参数：busy - 当前会话是否忙碌（忙碌时阻止新建/重命名/删除操作）；projects/currentProject/currentSessionId -
// 项目与会话相关状态；defaultProviderId/defaultModelId - 新会话默认供应商/模型；setCurrentProject/
// setProjectExpanded/setCurrentSessionId/setShowProjectModal/navigate - 状态与导航依赖；
// dialogService - 弹框服务（默认 nativeDialogService，测试时可替换）。
// 作用：把新建/重命名/删除会话三个底层操作包装成带错误处理（toast 提示）和 busy 判断的事件处理函数。
// 新建会话时若当前无项目则弹出新建项目弹窗；删除会话前会通过 dialogService 弹出二次确认。
// 返回：{ handleCreateSession, handleRenameSession, handleDeleteSession } 三个可直接绑定到 UI 事件的函数。
export function useSidebarSessionActions({
  busy,
  projects,
  currentProject,
  currentSessionId,
  defaultProviderId,
  defaultModelId,
  setCurrentProject,
  setProjectExpanded,
  setCurrentSessionId,
  setShowProjectModal,
  navigate,
  dialogService = nativeDialogService,
}: UseSidebarSessionActionsOptions) {
  const handleCreateSession = async () => {
    if (busy) {
      return
    }

    const targetProject = currentProject || projects[0]
    if (!targetProject) {
      setShowProjectModal(true)
      return
    }

    setCurrentProject(targetProject)
    setProjectExpanded(targetProject.id, true)

    try {
      const session = await createSidebarSession({
        projectId: targetProject.id,
        defaultProviderId,
        defaultModelId,
      })
      setCurrentSessionId(session.id)
      navigate('/agent')
    } catch (error) {
      console.error('Failed to create session:', error)
      dialogService.notifyError('创建聊天失败')
    }
  }

  const handleRenameSession = async (sessionId: string, nextTitle: string) => {
    if (busy) {
      return
    }

    const trimmed = nextTitle.trim()
    if (!trimmed) {
      return
    }

    try {
      await renameSession(sessionId, trimmed)
    } catch (error) {
      console.error('Failed to rename session:', error)
      dialogService.notifyError('重命名聊天失败')
      throw error
    }
  }

  const handleDeleteSession = async (session: SessionSummary) => {
    if (busy) {
      return
    }

    if (!(await dialogService.confirmAction(`确定删除聊天"${session.title}"吗？`, { variant: 'danger' }))) {
      return
    }

    try {
      await deleteSidebarSession({
        session,
        currentSessionId,
        setCurrentSessionId,
      })
    } catch (error) {
      console.error('Failed to delete session:', error)
      dialogService.notifyError('删除聊天失败')
    }
  }

  return {
    handleCreateSession,
    handleRenameSession,
    handleDeleteSession,
  }
}
