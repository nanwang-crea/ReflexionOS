/**
 * 文件功能：会话的供应商/模型选择解析逻辑
 * 文件描述：根据当前可用的 LLM 供应商列表、会话偏好设置与工作区默认设置，
 *           计算出会话实际应使用的供应商 ID 与模型 ID。
 * 核心逻辑：优先使用会话自身偏好（preferredProviderId/preferredModelId），
 *           偏好不可用（供应商未启用/模型不存在）时依次回退到工作区默认值，最终回退到列表第一项。
 */
import type { ProviderInstance, ProviderModel } from '@/types/llm'
import { getEnabledModels } from '@/utils/llmHelpers'

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

/**
 * 函数名：getAvailableProviders
 * 入参：
 *   - providers (ProviderInstance[]): 全部供应商实例列表
 * 功能：筛选出当前可用的供应商（已启用且至少有一个已启用模型）
 * 运行逻辑：过滤 enabled 为 true，且 getEnabledModels 返回结果非空的供应商
 * 出参：ProviderInstance[] - 可用供应商列表
 */
export function getAvailableProviders(providers: ProviderInstance[]) {
  return providers.filter((provider) => provider.enabled && getEnabledModels(provider).length > 0)
}

/**
 * 函数名：resolveProvider
 * 入参：
 *   - providers (ProviderInstance[]): 可选的供应商列表（通常是已过滤的可用供应商）
 *   - preferredProviderId (string | null | undefined): 期望优先使用的供应商 ID
 * 功能：从供应商列表中解析出最终应使用的供应商
 * 运行逻辑：若指定了 preferredProviderId 且能在列表中找到匹配项，则使用该项；
 *          否则回退为列表第一项，列表为空则返回 null
 * 出参：ProviderInstance | null - 解析出的供应商，或 null（无可用供应商）
 */
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

/**
 * 函数名：resolveModel
 * 入参：
 *   - models (ProviderModel[]): 当前供应商下可选的模型列表
 *   - preferredModelId (string | null | undefined): 期望优先使用的模型 ID
 *   - fallbackModelId (string | null | undefined): 次优先使用的模型 ID（如供应商默认模型）
 * 功能：从模型列表中解析出最终应使用的模型
 * 运行逻辑：依次尝试 preferredModelId、fallbackModelId 是否能在列表中匹配到，
 *          均未匹配时回退为列表第一项，列表为空则返回 null
 * 出参：ProviderModel | null - 解析出的模型，或 null（无可用模型）
 */
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

/**
 * 函数名：resolveSessionSelection
 * 入参：
 *   - options (ResolveSessionSelectionOptions): 包含 providers（全部供应商）、
 *     defaultProviderId/defaultModelId（工作区默认选择）、
 *     preferredProviderId/preferredModelId（会话偏好选择）
 * 功能：综合会话偏好与工作区默认设置，解析出该会话实际应使用的供应商与模型
 * 运行逻辑：
 *   1. 先筛选出可用供应商列表
 *   2. 供应商优先取会话偏好，缺省时取工作区默认，解析出 nextProvider
 *   3. 取 nextProvider 下已启用的模型列表
 *   4. 模型的兜底值：若 nextProvider 恰好是工作区默认供应商，则用工作区默认模型兜底；
 *      否则用 nextProvider 自身的 default_model_id 兜底
 *   5. 结合会话偏好模型与兜底模型解析出 nextModel
 * 出参：WorkspaceSelection - { providerId, modelId }，解析结果中任一项无法确定时为 null
 */
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
