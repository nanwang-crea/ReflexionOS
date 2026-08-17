/**
 * 文件功能：设置 Zustand Store
 * 文件描述：管理 LLM 提供方配置（providers、默认选择的 provider/model、是否已完成配置）
 * 以及 UI 偏好设置（是否默认展开处理过程、是否自动折叠处理过程）。
 * 核心逻辑：该 store 不做本地持久化，数据来源于后端接口拉取后通过 setLLMState / setUISetting 写入；
 * loaded / uiSettingsLoaded 分别标记两类设置是否已完成首次加载，供上层组件判断是否可以渲染。
 */

import { create } from 'zustand'
import { createEmptySelection } from '@/utils/llmHelpers'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

interface SettingsState {
  providers: ProviderInstance[]
  defaultSelection: DefaultLLMSelection
  defaultProviderId: string | null
  defaultModelId: string | null
  configured: boolean
  loaded: boolean
  showProcessExpanded: boolean
  autoCollapseProcess: boolean
  uiSettingsLoaded: boolean
  setLLMState: (payload: {
    providers: ProviderInstance[]
    selection: DefaultLLMSelection
  }) => void
  setUISetting: (payload: {
    showProcessExpanded: boolean
    autoCollapseProcess: boolean
  }) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  providers: [],
  defaultSelection: createEmptySelection(),
  defaultProviderId: null,
  defaultModelId: null,
  configured: false,
  loaded: false,
  showProcessExpanded: true,
  autoCollapseProcess: true,
  uiSettingsLoaded: false,

  /**
   * 写入 LLM 相关状态（提供方列表与默认选择）。
   * 入参：payload.providers（提供方实例数组）、payload.selection（默认选择的 provider/model 及是否已配置）
   * 运行逻辑：将 selection 拆解写入 defaultProviderId/defaultModelId/configured，并标记 loaded=true
   */
  setLLMState: ({ providers, selection }) => set({
    providers,
    defaultSelection: selection,
    defaultProviderId: selection.provider_id,
    defaultModelId: selection.model_id,
    configured: selection.configured,
    loaded: true,
  }),

  /**
   * 写入 UI 偏好设置。
   * 入参：payload.showProcessExpanded（是否默认展开处理过程）、payload.autoCollapseProcess（是否自动折叠处理过程）
   * 运行逻辑：直接覆盖写入两个偏好字段，并标记 uiSettingsLoaded=true
   */
  setUISetting: ({ showProcessExpanded, autoCollapseProcess }) => set({
    showProcessExpanded,
    autoCollapseProcess,
    uiSettingsLoaded: true,
  }),
}))
