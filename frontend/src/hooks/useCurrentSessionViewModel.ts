import { useCallback, useRef, useState } from 'react'
import { nativeDialogService } from '@/services/dialogService'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import type { ConversationMessage } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'
import type { Plan } from '@/types/conversation'
import type { ToolApprovalActionHandler } from '@/components/workspace/ToolTraceCard'
import { getRuntimeStatusDescriptor } from '@/components/workspace/runtimeStatus'
import { useSessionData } from './useSessionData'
import { useSessionSelection } from './useSessionSelection'

const REGENERATE_CONFIRM_MESSAGE = '重新生成回复？此消息之后的对话内容将被清除，AI 将基于当前上下文重新生成回复。'

export function useCurrentSessionViewModel(options: {
  messages: ConversationMessage[]
  isRunning: boolean
  isCancelling: boolean
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
  retryInfo: LlmRetryDto | null
  plan: Plan | null
  hasMore?: boolean
  onLoadMore?: (beforeTurnId: string) => void
  onReset: () => void | Promise<void>
  onApprovalAction?: ToolApprovalActionHandler
  editAndRerun?: (payload: {
    messageId: string
    newContent?: string | null
    providerId?: string | null
    modelId?: string | null
  }) => void
}) {
  const { configured, loaded } = useSettingsStore()
  const {
    currentProject,
    currentSessionSummary,
  } = useSessionData()
  const {
    selection,
    availableProviders,
    selectedModels,
    handleProviderChange,
    handleModelChange,
  } = useSessionSelection({
    preferredProviderId: currentSessionSummary?.preferredProviderId,
    preferredModelId: currentSessionSummary?.preferredModelId,
  })

  const isLoadingMoreRef = useRef(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  const handleLoadMore = useCallback(async (beforeTurnId: string) => {
    if (isLoadingMoreRef.current || !options.hasMore) return
    isLoadingMoreRef.current = true
    setIsLoadingMore(true)
    try {
      await options.onLoadMore?.(beforeTurnId)
    } finally {
      isLoadingMoreRef.current = false
      setIsLoadingMore(false)
    }
  }, [options])

  const handleEditMessage = useCallback((messageId: string, newContent: string) => {
    if (!currentSessionSummary) return
    options.editAndRerun?.({
      messageId,
      newContent,
      providerId: selection.providerId,
      modelId: selection.modelId,
    })
  }, [currentSessionSummary, options, selection.providerId, selection.modelId])

  const handleRegenerateMessage = useCallback(async (messageId: string) => {
    if (!currentSessionSummary) return
    const confirmed = await nativeDialogService.confirmAction(REGENERATE_CONFIRM_MESSAGE, { variant: 'danger' })
    if (!confirmed) return
    options.editAndRerun?.({
      messageId,
      newContent: null,
      providerId: selection.providerId,
      modelId: selection.modelId,
    })
  }, [currentSessionSummary, options, selection.providerId, selection.modelId])

  const runtimeStatus = getRuntimeStatusDescriptor({
    isRunning: options.isRunning,
    retryInfo: options.retryInfo,
    messages: options.messages,
  })

  return {
    currentProject,
    currentSession: currentSessionSummary,
    configured,
    loaded,
    selection,
    availableProviders,
    selectedModels,
    headerProps: {
      title: currentSessionSummary?.title || (currentProject ? currentProject.name : '选择项目开始'),
      projectPath: currentProject?.path,
      connectionStatus: options.connectionStatus,
      onReset: options.onReset,
    },
    transcriptProps: {
      loaded,
      configured,
      currentProject,
      currentSession: currentSessionSummary,
      messages: options.messages,
      isRunning: options.isRunning,
      retryInfo: options.retryInfo,
      plan: options.plan,
      runtimeStatus,
      onApprovalAction: options.onApprovalAction,
      onEditMessage: handleEditMessage,
      onRegenerateMessage: handleRegenerateMessage,
      hasMore: options.hasMore,
      isLoadingMore,
      onLoadMore: handleLoadMore,
    },
    inputProps: {
      disabled: !loaded || !configured || !currentProject || options.isRunning || options.isCancelling,
      isLoading: options.isRunning || options.isCancelling,
      canCancel: options.isRunning && !options.isCancelling,
      isCancelling: options.isCancelling,
      placeholder: currentProject ? '给当前项目开一个新任务...' : '请先选择项目',
      providerOptions: availableProviders.map((provider) => ({ id: provider.id, label: provider.name })),
      modelOptions: selectedModels.map((model) => ({ id: model.id, label: model.display_name })),
      selectedProviderId: selection.providerId,
      selectedModelId: selection.modelId,
      onProviderChange: handleProviderChange,
      onModelChange: handleModelChange,
      selectionDisabled: !loaded || options.isRunning || options.isCancelling || availableProviders.length === 0,
      runtimeStatusLabel: runtimeStatus.kind === 'idle' ? null : runtimeStatus.label,
    },
  }
}
