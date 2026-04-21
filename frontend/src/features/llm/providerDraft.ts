import type { DefaultLLMSelection, ProviderInstance, ProviderModel } from '@/types/llm'

function createLocalId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function createEmptyModel(): ProviderModel {
  return {
    id: createLocalId('model'),
    display_name: '',
    model_name: '',
    enabled: true,
  }
}

export function createEmptyProvider(): ProviderInstance {
  const model = createEmptyModel()

  return {
    id: createLocalId('provider'),
    name: '',
    provider_type: 'openai_compatible',
    api_key: '',
    base_url: '',
    models: [model],
    default_model_id: model.id,
    enabled: true,
  }
}

export function cloneProvider(provider: ProviderInstance): ProviderInstance {
  return {
    ...provider,
    models: provider.models.map((model) => ({ ...model })),
  }
}

export function getEnabledModels(provider: ProviderInstance | null | undefined) {
  return provider?.models.filter((model) => model.enabled) || []
}

export function normalizeProviderDraft(provider: ProviderInstance): ProviderInstance {
  const models = provider.models.map((model) => ({
    ...model,
    display_name: model.display_name.trim(),
    model_name: model.model_name.trim(),
  }))
  const defaultModelId = models.some((model) => model.id === provider.default_model_id)
    ? provider.default_model_id
    : models[0]?.id

  return {
    ...provider,
    name: provider.name.trim(),
    api_key: provider.api_key?.trim() || undefined,
    base_url: provider.base_url?.trim() || undefined,
    models,
    default_model_id: defaultModelId,
  }
}

export function validateProviderDraft(provider: ProviderInstance) {
  if (!provider.name.trim()) {
    return '供应商名称不能为空'
  }

  if (provider.models.length === 0) {
    return '请至少配置一个模型'
  }

  const hasEmptyModel = provider.models.some((model) => (
    !model.display_name.trim() || !model.model_name.trim()
  ))
  if (hasEmptyModel) {
    return '模型显示名称和模型名称不能为空'
  }

  return null
}

export function applyProviderToDefaultSelection(
  providers: ProviderInstance[],
  providerId: string,
  current: DefaultLLMSelection
): DefaultLLMSelection {
  const provider = providers.find((item) => item.id === providerId) || null
  const models = getEnabledModels(provider)

  return {
    ...current,
    provider_id: providerId,
    model_id: models.find((model) => model.id === provider?.default_model_id)?.id || models[0]?.id || null,
  }
}
