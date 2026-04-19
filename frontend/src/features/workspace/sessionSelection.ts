import type { ProviderInstance, ProviderModel } from '@/types/llm'

interface WorkspaceSelection {
  providerId: string | null
  modelId: string | null
}

interface ResolveSessionSelectionOptions {
  providers: ProviderInstance[]
  defaultProviderId?: string | null
  defaultModelId?: string | null
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

export function getEnabledModels(provider: ProviderInstance | null | undefined) {
  return provider?.models.filter((model) => model.enabled) || []
}

export function getAvailableProviders(providers: ProviderInstance[]) {
  return providers.filter((provider) => provider.enabled && getEnabledModels(provider).length > 0)
}

function resolveProvider(
  providers: ProviderInstance[],
  preferredProviderId?: string | null
) {
  if (preferredProviderId) {
    const matched = providers.find((provider) => provider.id === preferredProviderId)
    if (matched) {
      return matched
    }
  }

  return providers[0] || null
}

function resolveModel(
  models: ProviderModel[],
  preferredModelId?: string | null,
  fallbackModelId?: string | null
) {
  if (preferredModelId) {
    const matched = models.find((model) => model.id === preferredModelId)
    if (matched) {
      return matched
    }
  }

  if (fallbackModelId) {
    const matched = models.find((model) => model.id === fallbackModelId)
    if (matched) {
      return matched
    }
  }

  return models[0] || null
}

export function resolveSessionSelection(options: ResolveSessionSelectionOptions): WorkspaceSelection {
  const availableProviders = getAvailableProviders(options.providers)
  const preferredProviderId = options.preferredProviderId || options.defaultProviderId
  const nextProvider = resolveProvider(availableProviders, preferredProviderId)
  const nextModels = getEnabledModels(nextProvider)
  const fallbackModelId = nextProvider?.id === options.defaultProviderId
    ? options.defaultModelId
    : nextProvider?.default_model_id
  const nextModel = resolveModel(
    nextModels,
    options.preferredModelId,
    fallbackModelId
  )

  return {
    providerId: nextProvider?.id || null,
    modelId: nextModel?.id || null,
  }
}
