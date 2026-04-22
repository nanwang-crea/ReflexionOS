import { writeSessionPreferences as writeSessionPreferencesAction } from '@/features/sessions/sessionActions'
import { useProjectStore } from '@/stores/projectStore'
import type { SessionSummary } from '@/types/workspace'
import { useSessionActions } from './useSessionActions'

interface SelectionState {
  providerId: string | null
  modelId: string | null
}

interface SendMessageDependencies {
  currentProject: { id: string; name?: string; path?: string } | null
  currentSession: SessionSummary | null
  configured: boolean
  selection: SelectionState
  createSession: (
    projectId: string,
    payload: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => Promise<SessionSummary>
  writeSessionPreferences: (
    sessionId: string,
    payload: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => Promise<unknown>
  startExecutionRun: (payload: {
    sessionId: string
    message: string
    projectId: string
    providerId: string
    modelId: string
  }) => Promise<void>
  notify: (message: string) => void
}

export function createSendMessage(dependencies: SendMessageDependencies) {
  return async function sendMessage(message: string) {
    if (!message.trim()) {
      return
    }

    if (!dependencies.currentProject) {
      dependencies.notify('请先选择一个项目')
      return
    }

    if (!dependencies.configured) {
      dependencies.notify('请先在设置页面配置供应商、模型和默认项')
      return
    }

    if (!dependencies.selection.providerId || !dependencies.selection.modelId) {
      dependencies.notify('请先选择要使用的供应商和模型')
      return
    }

    const requiresFreshSession = (
      !dependencies.currentSession ||
      dependencies.currentSession.projectId !== dependencies.currentProject.id
    )
    let targetSession: SessionSummary

    if (requiresFreshSession) {
      targetSession = await dependencies.createSession(dependencies.currentProject.id, {
        preferredProviderId: dependencies.selection.providerId,
        preferredModelId: dependencies.selection.modelId,
      })
    } else {
      if (!dependencies.currentSession) {
        return
      }

      targetSession = dependencies.currentSession
    }

    if (!requiresFreshSession) {
      await dependencies.writeSessionPreferences(targetSession.id, {
        preferredProviderId: dependencies.selection.providerId,
        preferredModelId: dependencies.selection.modelId,
      })
    }

    await dependencies.startExecutionRun({
      sessionId: targetSession.id,
      message,
      projectId: dependencies.currentProject.id,
      providerId: dependencies.selection.providerId,
      modelId: dependencies.selection.modelId,
    })
  }
}

export function useSendMessage(options: {
  currentSession: SessionSummary | null
  configured: boolean
  selection: SelectionState
  startExecutionRun: SendMessageDependencies['startExecutionRun']
}) {
  const { currentProject } = useProjectStore()
  const { createSession } = useSessionActions()

  const sendMessage = createSendMessage({
    currentProject,
    currentSession: options.currentSession,
    configured: options.configured,
    selection: options.selection,
    createSession,
    writeSessionPreferences: writeSessionPreferencesAction,
    startExecutionRun: options.startExecutionRun,
    notify: (message) => {
      window.alert(message)
    },
  })

  return {
    sendMessage,
  }
}
