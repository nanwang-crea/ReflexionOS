// 文件功能：LLM 提供方/模型相关的小工具函数
// 文件描述：提供从 provider 中筛选启用模型、构造空的默认 LLM 选择对象等辅助函数
// 核心逻辑：均为无副作用的纯函数，供模型设置相关组件复用，避免重复实现相同逻辑
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

/**
 * 函数名：getEnabledModels
 * 入参：
 *   - provider (ProviderInstance | null | undefined): 提供方实例，可能为空
 * 功能：从提供方的模型列表中筛选出已启用（enabled）的模型
 * 运行逻辑：若 provider 为空则返回空数组；否则对 provider.models 按 enabled 字段过滤
 * 出参：ProviderModel[] - 已启用的模型列表（provider 为空时返回空数组）
 */
export function getEnabledModels(provider: ProviderInstance | null | undefined) {
  return provider?.models.filter((model) => model.enabled) || []
}

/**
 * 函数名：createEmptySelection
 * 入参：无
 * 功能：创建一个“未配置”状态的默认 LLM 选择对象
 * 运行逻辑：直接构造 provider_id/model_id 均为 null、configured 为 false 的对象
 * 出参：DefaultLLMSelection - 表示尚未配置默认提供方/模型的初始状态对象
 */
export function createEmptySelection(): DefaultLLMSelection {
  return {
    provider_id: null,
    model_id: null,
    configured: false,
  }
}
