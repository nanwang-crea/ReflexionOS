/**
 * useSendMessage coordinates session resolution and turn creation for the chat input.
 *
 * It validates send preconditions, creates the first session when needed, and
 * persists model/provider preferences before delegating to the websocket runtime.
 */
import { useCallback } from 'react'
import { writeSessionPreferences as writeSessionPreferencesAction } from '@/features/sessions/session.actions'
import { useSessionActions } from '@/features/sessions/hooks/useSessionActions'
import { useProjectStore } from '@/features/projects/stores/project.store'
import { nativeDialogService } from '@/services/dialogService'
import type { SessionSummary } from '@/types/workspace'

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
  startTurn: (payload: {
    sessionId: string
    message: string
    providerId: string
    modelId: string
    attachmentIds?: string[]
  }) => Promise<void> | void
  notify: (message: string) => void
}

async function resolveTargetSession(dependencies: SendMessageDependencies): Promise<SessionSummary | null> {
  /**
   * Resolves the session that should receive the next turn.
   *
   * It enforces workspace/model preconditions, creates a first session when needed,
   * and refreshes stored provider/model preferences on an existing session.
   */
  if (!dependencies.currentProject) {
    dependencies.notify('请先选择一个项目')
    return null
  }

  if (!dependencies.configured) {
    dependencies.notify('请先在设置页面配置供应商、模型和默认项')
    return null
  }

  if (!dependencies.selection.providerId || !dependencies.selection.modelId) {
    dependencies.notify('请先选择要使用的供应商和模型')
    return null
  }

  const requiresFreshSession = (
    !dependencies.currentSession ||
    dependencies.currentSession.projectId !== dependencies.currentProject.id
  )

  if (requiresFreshSession) {
    return dependencies.createSession(dependencies.currentProject.id, {
      preferredProviderId: dependencies.selection.providerId,
      preferredModelId: dependencies.selection.modelId,
    })
  }

  if (!dependencies.currentSession) {
    return null
  }

  await dependencies.writeSessionPreferences(dependencies.currentSession.id, {
    preferredProviderId: dependencies.selection.providerId,
    preferredModelId: dependencies.selection.modelId,
  })

  return dependencies.currentSession
}

export function createSendMessage(dependencies: SendMessageDependencies) {
  /**
   * Builds the send handler used by the workspace input.
   *
   * @param message - Raw text entered by the user. It may be empty when the turn contains images.
   * @param attachmentIds - Uploaded attachment IDs that should be attached to the turn.
   * @param targetSessionOverride - Pre-resolved session used to avoid creating the first session twice.
   */
  return async function sendMessage(
    message: string,
    attachmentIds?: string[],
    targetSessionOverride?: SessionSummary | null,
  ) {
    if (!message.trim() && (!attachmentIds || attachmentIds.length === 0)) {
      return
    }

    try {
      const targetSession = targetSessionOverride ?? await resolveTargetSession(dependencies)
      if (!targetSession) {
        return
      }
      const providerId = dependencies.selection.providerId
      const modelId = dependencies.selection.modelId
      if (!providerId || !modelId) {
        dependencies.notify('请先选择要使用的供应商和模型')
        return
      }

      await dependencies.startTurn({
        sessionId: targetSession.id,
        message,
        providerId,
        modelId,
        attachmentIds,
      })
    } catch (error) {
      console.error('Failed to send message:', error)
      const errorMessage = error instanceof Error ? error.message : '发送消息失败'
      dependencies.notify(errorMessage)
    }
  }
}

export function useSendMessage(options: {
  currentSession: SessionSummary | null
  configured: boolean
  selection: SelectionState
  startTurn: SendMessageDependencies['startTurn']
}) {
  const { currentProject } = useProjectStore()
  const { createSession } = useSessionActions()

  /**
   * Builds the dependency bundle lazily so each send uses the latest store state.
   */
  const buildDependencies = useCallback((): SendMessageDependencies => ({
    currentProject,
    currentSession: options.currentSession,
    configured: options.configured,
    selection: options.selection,
    createSession,
    writeSessionPreferences: writeSessionPreferencesAction,
    startTurn: options.startTurn,
    notify: nativeDialogService.notifyError,
  }), [currentProject, options.currentSession, options.configured, options.selection, createSession, options.startTurn])

  /**
   * Sends a turn through the shared createSendMessage flow.
   */
  const sendMessage = useCallback(async (
    message: string,
    attachmentIds?: string[],
    targetSessionOverride?: SessionSummary | null,
  ) => {
    const sendFn = createSendMessage(buildDependencies())
    await sendFn(message, attachmentIds, targetSessionOverride)
  }, [buildDependencies])

  /**
   * Resolves and, if necessary, creates the session ahead of attachment uploads.
   */
  const ensureSession = useCallback(async () => {
    return resolveTargetSession(buildDependencies())
  }, [buildDependencies])

  return {
    sendMessage,
    ensureSession,
  }
}
