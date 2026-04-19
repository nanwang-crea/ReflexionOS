import { describe, expect, it } from 'vitest'
import type { ProviderInstance } from '@/types/llm'
import { resolveSessionSelection } from './sessionSelection'

function createProvider(
  id: string,
  modelIds: string[],
  options: {
    enabled?: boolean
    defaultModelId?: string
  } = {}
): ProviderInstance {
  return {
    id,
    name: id,
    provider_type: 'openai_compatible',
    enabled: options.enabled ?? true,
    default_model_id: options.defaultModelId ?? modelIds[0],
    models: modelIds.map((modelId) => ({
      id: modelId,
      display_name: modelId,
      model_name: modelId,
      enabled: true,
    })),
  }
}

describe('resolveSessionSelection', () => {
  it('prefers the session selection when it is still valid', () => {
    const providers = [
      createProvider('provider-a', ['model-a1', 'model-a2']),
      createProvider('provider-b', ['model-b1']),
    ]

    expect(
      resolveSessionSelection({
        providers,
        defaultProviderId: 'provider-a',
        defaultModelId: 'model-a1',
        preferredProviderId: 'provider-b',
        preferredModelId: 'model-b1',
      })
    ).toEqual({
      providerId: 'provider-b',
      modelId: 'model-b1',
    })
  })

  it('falls back to the default selection when the preferred provider is unavailable', () => {
    const providers = [
      createProvider('provider-a', ['model-a1', 'model-a2']),
      createProvider('provider-b', ['model-b1'], { enabled: false }),
    ]

    expect(
      resolveSessionSelection({
        providers,
        defaultProviderId: 'provider-a',
        defaultModelId: 'model-a2',
        preferredProviderId: 'provider-b',
        preferredModelId: 'model-b1',
      })
    ).toEqual({
      providerId: 'provider-a',
      modelId: 'model-a2',
    })
  })

  it('falls back to the first enabled model when the preferred model is missing', () => {
    const providers = [
      createProvider('provider-a', ['model-a1', 'model-a2']),
    ]

    expect(
      resolveSessionSelection({
        providers,
        defaultProviderId: 'provider-a',
        defaultModelId: 'missing-model',
        preferredProviderId: 'provider-a',
        preferredModelId: 'missing-model',
      })
    ).toEqual({
      providerId: 'provider-a',
      modelId: 'model-a1',
    })
  })
})
