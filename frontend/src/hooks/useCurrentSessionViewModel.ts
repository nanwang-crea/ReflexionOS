import { useEffect, useRef } from 'react'
import { useSettingsStore } from '@/stores/settingsStore'
import type { ConversationMessage } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import { useSessionData } from './useSessionData'
import { useSessionSelection } from './useSessionSelection'

export function useCurrentSessionViewModel(options: {
  messages: ConversationMessage[]
  isRunning: boolean
  isCancelling: boolean
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
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
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
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
