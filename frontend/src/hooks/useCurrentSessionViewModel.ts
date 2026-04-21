import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { demoSessionHistoryById, isDemoMode } from '@/demo/demoData'
import { ensureLLMSettingsLoaded } from '@/features/llm/llmSettingsLoader'
import { useSessionStore } from '@/features/sessions/sessionStore'
import {
  ensureProjectSessionsLoaded,
  ensureSessionHistoryLoaded,
} from '@/features/sessions/sessionLoader'
import { flattenRoundsToItems, mergeRenderItems } from '@/features/workspace/messageFlow'
import {
  getAvailableProviders,
  getEnabledModels,
  resolveSessionSelection,
} from '@/features/workspace/sessionSelection'
import { useExecutionStore } from '@/stores/executionStore'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import type { SessionSummary, WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'

interface SelectionState {
  providerId: string | null
  modelId: string | null
}

export function useCurrentSessionViewModel(options: {
  overlayItems: WorkspaceChatItem[]
  activeRoundItems: WorkspaceSessionRound['items']
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
  onReset: () => void
  updateSessionPreferences: (
    sessionId: string,
    payload: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => Promise<unknown>
}) {
  const { currentProject } = useProjectStore()
  const { providers, defaultProviderId, defaultModelId, configured, loaded } = useSettingsStore()
  const currentSessionId = useWorkspaceStore((state) => state.currentSessionId)
  const setCurrentSessionId = useWorkspaceStore((state) => state.setCurrentSessionId)
  const { status } = useExecutionStore()
  const sessionsByProjectId = useSessionStore((state) => state.sessionsByProjectId)
  const historyBySessionId = useSessionStore((state) => state.historyBySessionId)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const demoMode = isDemoMode()

  const [selection, setSelection] = useState<SelectionState>({
    providerId: null,
    modelId: null,
  })

  const projectSessions = currentProject ? sessionsByProjectId[currentProject.id] || [] : []
  const currentSessionSummary = useMemo(
    () => projectSessions.find((session) => session.id === currentSessionId) || null,
    [currentSessionId, projectSessions]
  )
  const persistedRounds = useMemo(() => {
    if (!currentSessionSummary) {
      return []
    }

    if (demoMode) {
      return demoSessionHistoryById[currentSessionSummary.id] || []
    }

    return historyBySessionId[currentSessionSummary.id] || []
  }, [currentSessionSummary, demoMode, historyBySessionId])

  const availableProviders = useMemo(() => getAvailableProviders(providers), [providers])
  const selectedProvider = useMemo(
    () => availableProviders.find((provider) => provider.id === selection.providerId) || null,
    [availableProviders, selection.providerId]
  )
  const selectedModels = useMemo(() => getEnabledModels(selectedProvider), [selectedProvider])
  const renderItems = useMemo(
    () => mergeRenderItems(
      [...flattenRoundsToItems(persistedRounds), ...options.activeRoundItems],
      options.overlayItems
    ),
    [options.activeRoundItems, options.overlayItems, persistedRounds]
  )

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [renderItems])

  useEffect(() => {
    ensureLLMSettingsLoaded().catch((error) => {
      console.error('Failed to load LLM settings:', error)
    })
  }, [])

  useEffect(() => {
    if (!currentProject || demoMode) {
      return
    }

    ensureProjectSessionsLoaded(currentProject.id).catch((error) => {
      console.error('Failed to load project sessions:', error)
    })
  }, [currentProject, demoMode])

  useEffect(() => {
    if (!currentSessionId || demoMode) {
      return
    }

    if (!currentSessionSummary) {
      setCurrentSessionId(null)
      return
    }

    ensureSessionHistoryLoaded(currentSessionSummary.id).catch((error) => {
      console.error('Failed to load session history:', error)
    })
  }, [currentSessionId, currentSessionSummary, demoMode, setCurrentSessionId])

  useEffect(() => {
    const nextSelection = resolveSessionSelection({
      providers: availableProviders,
      defaultProviderId,
      defaultModelId,
      preferredProviderId: currentSessionSummary?.preferredProviderId,
      preferredModelId: currentSessionSummary?.preferredModelId,
    })

    setSelection((current) => (
      current.providerId === nextSelection.providerId && current.modelId === nextSelection.modelId
        ? current
        : nextSelection
    ))

    if (
        currentSessionId &&
        nextSelection.providerId &&
        nextSelection.modelId &&
        (
          currentSessionSummary?.preferredProviderId !== nextSelection.providerId ||
          currentSessionSummary?.preferredModelId !== nextSelection.modelId
        )
    ) {
      options.updateSessionPreferences(currentSessionId, {
        preferredProviderId: nextSelection.providerId,
        preferredModelId: nextSelection.modelId,
      }).catch((error) => {
        console.error('Failed to update session preferences:', error)
      })
    }
  }, [
    availableProviders,
    currentSessionSummary?.preferredModelId,
    currentSessionSummary?.preferredProviderId,
    currentSessionId,
    defaultModelId,
    defaultProviderId,
    options,
  ])

  const handleProviderChange = useCallback((providerId: string | null) => {
    if (!providerId) {
      setSelection({ providerId: null, modelId: null })
      return
    }

    const provider = availableProviders.find((item) => item.id === providerId) || null
    const nextModels = getEnabledModels(provider)
    const nextSelection = resolveSessionSelection({
      providers: provider ? [provider] : [],
      defaultProviderId: provider?.id || null,
      defaultModelId: provider?.default_model_id || null,
      preferredProviderId: provider?.id || null,
      preferredModelId: provider?.default_model_id || null,
    })

    if (!nextSelection.modelId && nextModels[0]) {
      nextSelection.modelId = nextModels[0].id
    }

    setSelection(nextSelection)

    if (currentSessionId && nextSelection.modelId) {
      options.updateSessionPreferences(currentSessionId, {
        preferredProviderId: nextSelection.providerId,
        preferredModelId: nextSelection.modelId,
      }).catch((error) => {
        console.error('Failed to update session preferences:', error)
      })
    }
  }, [availableProviders, currentSessionId, options])

  const handleModelChange = useCallback((modelId: string | null) => {
    if (!selection.providerId) {
      return
    }

    const nextSelection = {
      providerId: selection.providerId,
      modelId,
    }

    setSelection(nextSelection)

    if (currentSessionId && nextSelection.modelId) {
      options.updateSessionPreferences(currentSessionId, {
        preferredProviderId: nextSelection.providerId,
        preferredModelId: nextSelection.modelId,
      }).catch((error) => {
        console.error('Failed to update session preferences:', error)
      })
    }
  }, [currentSessionId, options, selection.providerId])

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
