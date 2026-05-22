import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

export function getEnabledModels(provider: ProviderInstance | null | undefined) {
  return provider?.models.filter((model) => model.enabled) || []
}

export function createEmptySelection(): DefaultLLMSelection {
  return {
    provider_id: null,
    model_id: null,
    configured: false,
  }
}
