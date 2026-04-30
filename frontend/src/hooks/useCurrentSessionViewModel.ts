import { useCallback, useEffect, useRef, useState } from 'react'
import { useSettingsStore } from '@/stores/settingsStore'
import type { ConversationMessage } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'
import type { Plan } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import { shouldFollowTranscript } from '@/features/workspace/autoScroll'
import { useSessionData } from './useSessionData'
import { useSessionSelection } from './useSessionSelection'

export function useCurrentSessionViewModel(options: {
  messages: ConversationMessage[]
  isRunning: boolean
  isCancelling: boolean
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
  retryInfo: LlmRetryDto | null
  plan: Plan | null
  onReset: () => void
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
  const transcriptScrollRef = useRef<HTMLDivElement | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const shouldAutoScrollRef = useRef(true)
  const [isAtBottom, setIsAtBottom] = useState(true)

  const handleTranscriptScroll = useCallback(() => {
    const container = transcriptScrollRef.current
    if (!container) {
      return
    }

    const shouldFollow = shouldFollowTranscript({
      scrollTop: container.scrollTop,
      clientHeight: container.clientHeight,
      scrollHeight: container.scrollHeight,
    })
    shouldAutoScrollRef.current = shouldFollow
    setIsAtBottom(shouldFollow)
  }, [])

  const scrollToBottom = useCallback(() => {
    shouldAutoScrollRef.current = true
    setIsAtBottom(true)
    messagesEndRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [])

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return
    }
    messagesEndRef.current?.scrollIntoView({ block: 'end' })
    setIsAtBottom(true)
  }, [options.messages])

  return {
    currentProject,
    currentSession: currentSessionSummary as SessionSummary | null,
    configured,
    loaded,
    selection,
    messagesEndRef,
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
      transcriptScrollRef,
      onTranscriptScroll: handleTranscriptScroll,
      isAtBottom,
      onScrollToBottom: scrollToBottom,
      messagesEndRef,
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
    },
  }
}
