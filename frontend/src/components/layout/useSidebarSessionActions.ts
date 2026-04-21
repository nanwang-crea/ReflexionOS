import { createSession, deleteSession, renameSession } from '@/features/sessions/sessionActions'
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

export async function createSidebarSession({
  projectId,
  defaultProviderId,
  defaultModelId,
}: CreateSidebarSessionOptions) {
  return createSession(projectId, {
    preferredProviderId: defaultProviderId,
    preferredModelId: defaultModelId,
  })
}

export async function deleteSidebarSession({
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
}

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
      alert('创建聊天失败')
    }
  }

  const handleRenameSession = async (session: SessionSummary) => {
    if (busy) {
      return
    }

    const nextTitle = prompt('重命名聊天', session.title)?.trim()
    if (!nextTitle || nextTitle === session.title) {
      return
    }

    try {
      await renameSession(session.id, nextTitle)
    } catch (error) {
      console.error('Failed to rename session:', error)
      alert('重命名聊天失败')
    }
  }

  const handleDeleteSession = async (session: SessionSummary) => {
    if (busy) {
      return
    }

    if (!confirm(`确定删除聊天“${session.title}”吗？`)) {
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
      alert('删除聊天失败')
    }
  }

  return {
    handleCreateSession,
    handleRenameSession,
    handleDeleteSession,
  }
}
