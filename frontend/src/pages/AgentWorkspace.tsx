import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { isDemoMode } from '@/demo/demoData'
import { ChatInput } from '@/components/chat/ChatInput'
import { WorkspaceHeader } from '@/components/workspace/WorkspaceHeader'
import { WorkspaceTranscript } from '@/components/workspace/WorkspaceTranscript'
import { ensureLLMSettingsLoaded } from '@/features/llm/llmSettingsLoader'
import { useExecutionRuntime } from '@/hooks/useExecutionRuntime'
import { mergeRenderItems } from '@/features/workspace/messageFlow'
import {
  getAvailableProviders,
  getEnabledModels,
  resolveSessionSelection,
} from '@/features/workspace/sessionSelection'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'

export default function AgentWorkspace() {
  const { currentProject } = useProjectStore()
  const {
    providers,
    defaultProviderId,
    defaultModelId,
    configured,
    loaded,
  } = useSettingsStore()
  const {
    sessions,
    currentSessionId,
    createSession,
    saveSessionItems,
    updateSessionPreferences,
  } = useWorkspaceStore()
  const { status } = useExecutionStore()

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === currentSessionId) || null,
    [currentSessionId, sessions]
  )
  const demoMode = isDemoMode()

  const [selection, setSelection] = useState<{ providerId: string | null; modelId: string | null }>({
    providerId: null,
    modelId: null,
  })
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const {
    overlayItems,
    connectionStatus,
    startExecutionRun,
    handleCancel,
    resetExecutionRuntime,
  } = useExecutionRuntime(currentSessionId, demoMode ? 'connected' : 'disconnected')

  const availableProviders = useMemo(
    () => getAvailableProviders(providers),
    [providers]
  )

  const selectedProvider = useMemo(
    () => availableProviders.find((provider) => provider.id === selection.providerId) || null,
    [availableProviders, selection.providerId]
  )

  const selectedModels = useMemo(
    () => getEnabledModels(selectedProvider),
    [selectedProvider]
  )

  const renderItems = useMemo(
    () => mergeRenderItems(currentSession?.items || [], overlayItems),
    [currentSession?.items, overlayItems]
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
    const nextSelection = resolveSessionSelection({
      providers: availableProviders,
      defaultProviderId,
      defaultModelId,
      preferredProviderId: currentSession?.preferredProviderId,
      preferredModelId: currentSession?.preferredModelId,
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
        currentSession?.preferredProviderId !== nextSelection.providerId ||
        currentSession?.preferredModelId !== nextSelection.modelId
      )
    ) {
      updateSessionPreferences(currentSessionId, {
        preferredProviderId: nextSelection.providerId,
        preferredModelId: nextSelection.modelId,
      })
    }
  }, [
    availableProviders,
    currentSession?.preferredModelId,
    currentSession?.preferredProviderId,
    currentSessionId,
    defaultModelId,
    defaultProviderId,
    updateSessionPreferences,
  ])

  const handleProviderChange = useCallback((providerId: string | null) => {
    if (!providerId) {
      setSelection({
        providerId: null,
        modelId: null,
      })
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
      updateSessionPreferences(currentSessionId, {
        preferredProviderId: nextSelection.providerId,
        preferredModelId: nextSelection.modelId,
      })
    }
  }, [availableProviders, currentSessionId, updateSessionPreferences])

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
      updateSessionPreferences(currentSessionId, {
        preferredProviderId: nextSelection.providerId,
        preferredModelId: nextSelection.modelId,
      })
    }
  }, [currentSessionId, selection.providerId, updateSessionPreferences])

  const handleSend = useCallback(async (message: string) => {
    if (!message.trim()) {
      return
    }

    if (!currentProject) {
      alert('请先选择一个项目')
      return
    }

    if (!configured) {
      alert('请先在设置页面配置供应商、模型和默认项')
      return
    }

    if (!selection.providerId || !selection.modelId) {
      alert('请先选择要使用的供应商和模型')
      return
    }

    const requiresFreshSession = !currentSession || currentSession.projectId !== currentProject.id
    const targetSession = requiresFreshSession
      ? createSession(
          currentProject.id,
          undefined,
          selection.providerId,
          selection.modelId
        )
      : currentSession

    if (!requiresFreshSession) {
      updateSessionPreferences(targetSession.id, {
        preferredProviderId: selection.providerId,
        preferredModelId: selection.modelId,
      })
    }

    await startExecutionRun({
      sessionId: targetSession.id,
      message,
      projectPath: currentProject.path,
      providerId: selection.providerId,
      modelId: selection.modelId,
    })
  }, [
    configured,
    createSession,
    currentProject,
    currentSession,
    selection.modelId,
    selection.providerId,
    startExecutionRun,
    updateSessionPreferences,
  ])

  const handleReset = useCallback(() => {
    resetExecutionRuntime()

    if (currentSessionId) {
      saveSessionItems(currentSessionId, [])
    }
  }, [currentSessionId, resetExecutionRuntime, saveSessionItems])

  const inputBusy = status === 'running' || status === 'cancelling'
  const providerOptions = availableProviders.map((provider) => ({
    id: provider.id,
    label: provider.name,
  }))
  const modelOptions = selectedModels.map((model) => ({
    id: model.id,
    label: model.display_name,
  }))

  return (
    <div className="flex h-full flex-col bg-white">
      <WorkspaceHeader
        title={currentSession?.title || (currentProject ? currentProject.name : '选择项目开始')}
        projectPath={currentProject?.path}
        connectionStatus={connectionStatus}
        onReset={handleReset}
      />

      <WorkspaceTranscript
        loaded={loaded}
        configured={configured}
        currentProject={currentProject}
        currentSession={currentSession}
        items={renderItems}
        messagesEndRef={messagesEndRef}
      />

      <div className="border-t border-gray-200 bg-white p-4">
        <ChatInput
          onSend={handleSend}
          onCancel={handleCancel}
          disabled={!loaded || !configured || !currentProject || inputBusy}
          isLoading={inputBusy}
          canCancel={status === 'running'}
          isCancelling={status === 'cancelling'}
          placeholder={currentProject ? '给当前项目开一个新任务...' : '请先选择项目'}
          providerOptions={providerOptions}
          modelOptions={modelOptions}
          selectedProviderId={selection.providerId}
          selectedModelId={selection.modelId}
          onProviderChange={handleProviderChange}
          onModelChange={handleModelChange}
          selectionDisabled={!loaded || inputBusy || providerOptions.length === 0}
        />
        {!currentProject && (
          <p className="mt-2 text-sm text-gray-500">请先从左侧选择一个项目</p>
        )}
      </div>
    </div>
  )
}
