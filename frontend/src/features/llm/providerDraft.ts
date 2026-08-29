/**
 * 文件功能：LLM 供应商草稿（表单编辑态）的构造、克隆、规范化与校验工具函数
 * 文件描述：为设置页面的供应商编辑表单提供纯函数支持：生成空白供应商/模型草稿、
 *          深拷贝供应商对象（避免直接修改 store 中的数据）、trim 规范化用户输入、
 *          校验必填字段、以及切换默认供应商时联动计算默认模型选择。
 * 核心逻辑：全部为无副作用的纯函数，方便在 controller/action 层任意组合调用和单测。
 */
import type { DefaultLLMSelection, ProviderInstance, ProviderModel } from '@/types/llm'
import { getEnabledModels } from '@/utils/llmHelpers'

/**
 * 函数名：createLocalId
 * 入参：
 *   - prefix (string): id 前缀，用于区分是 model 还是 provider
 * 功能：生成一个本地临时唯一 id（未持久化到后端前使用）
 * 运行逻辑：拼接前缀、当前时间戳、随机字符串
 * 出参：string - 形如 "prefix-时间戳-随机串" 的本地 id
 */
function createLocalId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * 函数名：createEmptyModel
 * 入参：无
 * 功能：创建一个空白的模型草稿（用于表单中"添加模型"）
 * 运行逻辑：生成本地 id，其余字段为空字符串/默认启用
 * 出参：ProviderModel - 空白模型对象
 */
export function createEmptyModel(): ProviderModel {
  return {
    id: createLocalId('model'),
    display_name: '',
    model_name: '',
    enabled: true,
  }
}

/**
 * 函数名：createEmptyProvider
 * 入参：无
 * 功能：创建一个空白的供应商草稿（用于表单中"新建供应商"），默认自带一个空白模型
 * 运行逻辑：先调用 createEmptyModel 生成一个默认模型，再构造供应商对象，
 *          default_model_id 直接指向这个新建模型的 id
 * 出参：ProviderInstance - 空白供应商对象
 */
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

/**
 * 函数名：cloneProvider
 * 入参：
 *   - provider (ProviderInstance): 待克隆的供应商对象
 * 功能：深拷贝供应商对象（包括其 models 数组），避免直接修改 store 中的原始数据
 * 运行逻辑：浅拷贝顶层字段，models 数组逐项浅拷贝
 * 出参：ProviderInstance - 克隆后的新对象
 */
export function cloneProvider(provider: ProviderInstance): ProviderInstance {
  return {
    ...provider,
    models: provider.models.map((model) => ({ ...model })),
  }
}

/**
 * 函数名：normalizeProviderDraft
 * 入参：
 *   - provider (ProviderInstance): 表单中编辑的供应商草稿（可能含首尾空格）
 * 功能：在提交保存前，对供应商草稿做字段规范化（trim 空白），并将空字符串的
 *      api_key/base_url 转为 undefined（避免向后端提交空字符串）
 * 运行逻辑：对 models 数组中每个模型的 display_name/model_name 做 trim，
 *          对顶层 name/api_key/base_url 做 trim（api_key/base_url 为空时转 undefined）
 * 出参：ProviderInstance - 规范化后的供应商对象
 */
export function normalizeProviderDraft(provider: ProviderInstance): ProviderInstance {
  const models = provider.models.map((model) => ({
    ...model,
    display_name: model.display_name.trim(),
    model_name: model.model_name.trim(),
  }))

  return {
    ...provider,
    name: provider.name.trim(),
    api_key: provider.api_key?.trim() || undefined,
    base_url: provider.base_url?.trim() || undefined,
    models,
  }
}

/**
 * 函数名：validateProviderDraft
 * 入参：
 *   - provider (ProviderInstance): 待校验的供应商草稿
 * 功能：校验供应商草稿是否满足保存前的基本要求
 * 运行逻辑：依次检查名称非空、至少有一个模型、所有模型的显示名称与模型名称均非空，
 *          任一检查不通过立即返回对应的中文错误提示
 * 出参：string | null - 校验失败时返回错误提示文案，校验通过返回 null
 */
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

/**
 * 函数名：applyProviderToDefaultSelection
 * 入参：
 *   - providers (ProviderInstance[]): 完整的供应商列表
 *   - providerId (string): 用户新选择的默认供应商 id
 *   - current (DefaultLLMSelection): 当前的默认选择（用于保留其他字段）
 * 功能：当用户切换"默认供应商"下拉框时，联动计算出对应的默认模型 id
 * 运行逻辑：从列表中找到对应供应商，取其已启用的模型列表；
 *          优先沿用该供应商自身的 default_model_id（若在启用列表中），
 *          否则回退取启用列表的第一个模型，都没有则为 null
 * 出参：DefaultLLMSelection - 更新了 provider_id/model_id 后的新选择对象
 */
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
