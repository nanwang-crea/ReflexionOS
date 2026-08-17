// 文件功能：管理会话的“供应商 + 模型”选择状态
// 文件描述：根据用户设置中的可用供应商列表、默认供应商/模型、以及调用方期望的偏好供应商/模型，
// 解析出当前应使用的供应商与模型，并提供切换供应商/模型的回调
// 核心逻辑：可用供应商变化或偏好参数变化时通过 resolveSessionSelection 重新解析一次选择结果；
// 用户手动切换供应商时按新供应商的默认模型重新解析，切换模型时仅替换 modelId
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAvailableProviders,
  resolveSessionSelection,
} from '@/features/workspace/sessionSelection'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import type { ProviderInstance } from '@/types/llm'
import { getEnabledModels } from '@/utils/llmHelpers'

export interface SessionSelectionState {
  providerId: string | null
  modelId: string | null
}

interface UseSessionSelectionOptions {
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

// 函数名：resolveSelectionForProvider
// 入参：
//   - provider (ProviderInstance | null): 目标供应商实例，为 null 表示未选择供应商
// 功能：根据指定供应商解析出应选中的供应商 ID 与模型 ID
// 运行逻辑：
//   1. 取出该供应商下已启用的模型列表
//   2. 调用 resolveSessionSelection，把该供应商既当作默认值又当作偏好值传入
//   3. 若解析结果没有 modelId，但启用模型列表非空，则兜底选中第一个启用模型
// 出参：SessionSelectionState - { providerId, modelId }
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

// 函数名：useSessionSelection
// 入参：
//   - options.preferredProviderId (string | null, 可选): 调用方期望优先选中的供应商 ID
//   - options.preferredModelId (string | null, 可选): 调用方期望优先选中的模型 ID
// 功能：维护并返回当前应使用的供应商/模型选择状态，以及可用供应商、当前供应商下的可用模型、
// 切换供应商/模型的回调方法
// 运行逻辑：
//   1. 从 settingsStore 读取全部供应商配置与默认供应商/模型 ID
//   2. 用 useMemo 计算可用供应商列表、当前选中的供应商对象、该供应商下已启用的模型列表
//   3. 当可用供应商列表或默认值/偏好值变化时，重新调用 resolveSessionSelection 解析选择结果；
//      仅当结果与当前状态不同才触发 setSelection，避免无意义的重渲染
//   4. handleProviderChange：切换供应商时按新供应商重新解析模型；传 null 则清空选择
//   5. handleModelChange：仅在已有 providerId 的前提下更新 modelId
// 出参：{ selection, availableProviders, selectedModels, handleProviderChange, handleModelChange }
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
