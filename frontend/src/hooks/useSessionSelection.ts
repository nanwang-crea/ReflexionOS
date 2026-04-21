import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAvailableProviders,
  getEnabledModels,
  resolveSessionSelection,
} from '@/features/workspace/sessionSelection'
import { useSettingsStore } from '@/stores/settingsStore'
import type { ProviderInstance } from '@/types/llm'

export interface SessionSelectionState {
  providerId: string | null
  modelId: string | null
}

interface UseSessionSelectionOptions {
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

function resolveSelectionForProvider(provider: ProviderInstance | null): SessionSelectionState {
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

  return nextSelection
}

export function useSessionSelection(options: UseSessionSelectionOptions) {
  const { providers, defaultProviderId, defaultModelId } = useSettingsStore()
  const [selection, setSelection] = useState<SessionSelectionState>({
    providerId: null,
    modelId: null,
  })

  const availableProviders = useMemo(() => getAvailableProviders(providers), [providers])
  const selectedProvider = useMemo(
    () => availableProviders.find((provider) => provider.id === selection.providerId) || null,
    [availableProviders, selection.providerId]
  )
  const selectedModels = useMemo(() => getEnabledModels(selectedProvider), [selectedProvider])

  useEffect(() => {
    const nextSelection = resolveSessionSelection({
      providers: availableProviders,
      defaultProviderId,
      defaultModelId,
      preferredProviderId: options.preferredProviderId,
      preferredModelId: options.preferredModelId,
    })

    setSelection((current) => (
      current.providerId === nextSelection.providerId && current.modelId === nextSelection.modelId
        ? current
        : nextSelection
    ))

  }, [
    availableProviders,
    defaultModelId,
    defaultProviderId,
    options.preferredModelId,
    options.preferredProviderId,
  ])

  const handleProviderChange = useCallback((providerId: string | null) => {
    if (!providerId) {
      setSelection({ providerId: null, modelId: null })
      return
    }

    const provider = availableProviders.find((item) => item.id === providerId) || null
    const nextSelection = resolveSelectionForProvider(provider)
    setSelection(nextSelection)
  }, [availableProviders])

  const handleModelChange = useCallback((modelId: string | null) => {
    if (!selection.providerId) {
      return
    }

    const nextSelection = {
      providerId: selection.providerId,
      modelId,
    }

    setSelection(nextSelection)
  }, [selection.providerId])

  return {
    selection,
    availableProviders,
    selectedModels,
    handleProviderChange,
    handleModelChange,
  }
}
