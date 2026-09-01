/**
 * 文件功能：sessionSelection.ts 单元测试
 * 文件描述：验证 resolveSessionSelection 在“会话偏好有效”“偏好供应商不可用回退默认”
 *           “偏好模型缺失回退首个可用模型”等场景下的解析结果是否正确。
 * 核心逻辑：用 createProvider 辅助函数构造测试用供应商数据，对 resolveSessionSelection 的返回值做断言。
 */
import { describe, expect, it } from 'vitest'
import type { ProviderInstance } from '@/types/llm'
import { resolveSessionSelection } from '../sessionSelection'

/**
 * 函数名：createProvider
 * 入参：
 *   - id (string): 供应商 ID
 *   - modelIds (string[]): 该供应商下的模型 ID 列表
 *   - options ({ enabled?, defaultModelId? }): 可选配置，enabled 默认 true，defaultModelId 默认取 modelIds 第一项
 * 功能：构造测试用的 ProviderInstance 对象
 * 运行逻辑：按传入参数拼装供应商对象，models 字段由 modelIds 映射为启用状态的模型对象数组
 * 出参：ProviderInstance - 测试用供应商实例
 */
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
