import { useExecutionStore } from '@/stores/executionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import type { SessionSummary, WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'
import { useSessionData } from './useSessionData'
import { useSessionRenderItems } from './useSessionRenderItems'
import { useSessionSelection } from './useSessionSelection'

export function useCurrentSessionViewModel(options: {
  overlayItems: WorkspaceChatItem[]
  activeRoundItems: WorkspaceSessionRound['items']
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
  onReset: () => void
}) {
  const { configured, loaded } = useSettingsStore()
  const { status } = useExecutionStore()
  const {
    currentProject,
    currentSessionSummary,
    persistedRounds,
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
  const { messagesEndRef, renderItems } = useSessionRenderItems({
    persistedRounds,
    activeRoundItems: options.activeRoundItems,
    overlayItems: options.overlayItems,
  })

  return {
    currentProject,
    currentSession: currentSessionSummary as SessionSummary | null,
    configured,
    loaded,
    status,
    selection,
    messagesEndRef,
    renderItems,
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
      items: renderItems,
      messagesEndRef,
    },
    inputProps: {
      disabled: !loaded || !configured || !currentProject || status === 'running' || status === 'cancelling',
      isLoading: status === 'running' || status === 'cancelling',
      canCancel: status === 'running',
      isCancelling: status === 'cancelling',
      placeholder: currentProject ? '给当前项目开一个新任务...' : '请先选择项目',
      providerOptions: availableProviders.map((provider) => ({ id: provider.id, label: provider.name })),
      modelOptions: selectedModels.map((model) => ({ id: model.id, label: model.display_name })),
      selectedProviderId: selection.providerId,
      selectedModelId: selection.modelId,
      onProviderChange: handleProviderChange,
      onModelChange: handleModelChange,
      selectionDisabled: !loaded || status === 'running' || status === 'cancelling' || availableProviders.length === 0,
    },
  }
}
