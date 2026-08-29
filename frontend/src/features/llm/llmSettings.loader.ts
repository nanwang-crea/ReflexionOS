/**
 * 文件功能：LLM 设置的加载与缓存管理
 * 文件描述：封装"确保 LLM 设置（供应商列表 + 默认模型选择）已加载"的逻辑，
 *          带请求去重（同一时间只发一次请求）和缓存复用（已加载则直接返回），
 *          并提供重置 store 的方法。
 * 核心逻辑：createLLMSettingsLoader 是一个工厂函数，通过闭包变量 inFlight 记录
 *          当前是否有请求在途，避免并发调用时重复发起网络请求；加载结果写入
 *          settings.store 供全局复用。
 */
import { llmApi } from './api/llm.api'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import type { DefaultLLMSelection, ProviderInstance } from '@/types/llm'

interface LoadedLLMSettings {
  providers: ProviderInstance[]
  selection: DefaultLLMSelection
}

interface LLMSettingsLoaderState {
  loaded: boolean
  providers: ProviderInstance[]
  defaultSelection: DefaultLLMSelection
}

interface CreateLLMSettingsLoaderOptions {
  getProviders: () => Promise<ProviderInstance[]>
  getDefaultSelection: () => Promise<DefaultLLMSelection>
  getState: () => LLMSettingsLoaderState
  setLLMState: (settings: LoadedLLMSettings) => void
}

/**
 * 函数名：createLoadedSnapshot
 * 入参：
 *   - state (LLMSettingsLoaderState): 当前 store 中的 LLM 设置状态
 * 功能：从 store 状态中提取出对外返回的精简快照（仅 providers 和 selection）
 * 运行逻辑：直接取字段组装新对象，不做校验
 * 出参：LoadedLLMSettings - 精简后的设置快照
 */
function createLoadedSnapshot(state: LLMSettingsLoaderState): LoadedLLMSettings {
  return {
    providers: state.providers,
    selection: state.defaultSelection,
  }
}

/**
 * 函数名：createLLMSettingsLoader
 * 入参：
 *   - options (CreateLLMSettingsLoaderOptions): 依赖注入的配置，包含获取供应商列表/
 *     默认选择的方法、读取当前 store 状态的方法、写入 store 的方法
 * 功能：创建一个"确保 LLM 设置已加载"的加载函数（工厂函数，便于测试时注入 mock 依赖）
 * 运行逻辑：返回的 ensureLLMSettingsLoaded 函数：
 *   1. 若非强制刷新且 store 已标记为已加载，直接返回当前快照，不发请求；
 *   2. 若已有请求在途（inFlight 不为空），直接返回该请求的 Promise，实现请求去重；
 *   3. 否则并发发起 getProviders 和 getDefaultSelection 请求，成功后写入 store，
 *      并在 finally 中清空 inFlight 标记（无论成功失败都要清空，避免永久卡住）。
 * 出参：(options?: { force?: boolean }) => Promise<LoadedLLMSettings> - 加载函数
 */
function createLLMSettingsLoader(options: CreateLLMSettingsLoaderOptions) {
  let inFlight: Promise<LoadedLLMSettings> | null = null

  return async function ensureLLMSettingsLoaded({ force = false }: { force?: boolean } = {}) {
    const state = options.getState()
    if (!force && state.loaded) {
      return createLoadedSnapshot(state)
    }

    if (inFlight) {
      return inFlight
    }

    inFlight = (async () => {
      const settings = {
        providers: await options.getProviders(),
        selection: await options.getDefaultSelection(),
      }

      options.setLLMState(settings)
      return settings
    })().finally(() => {
      inFlight = null
    })

    return inFlight
  }
}

// 使用真实的 llmApi 和 settingsStore 构建的默认加载器实例
const ensureLLMSettingsLoadedInternal = createLLMSettingsLoader({
  getProviders: async () => {
    const response = await llmApi.getProviders()
    return response.data
  },
  getDefaultSelection: async () => {
    const response = await llmApi.getDefaultSelection()
    return response.data
  },
  getState: () => useSettingsStore.getState(),
  setLLMState: (settings) => useSettingsStore.getState().setLLMState(settings),
})

/**
 * 函数名：ensureLLMSettingsLoaded
 * 入参：
 *   - options ({ force?: boolean } | undefined): force 为 true 时强制重新请求，忽略缓存
 * 功能：对外暴露的入口函数，确保 LLM 设置已加载到 store 中
 * 运行逻辑：直接委托给内部构建好的加载器实例 ensureLLMSettingsLoadedInternal
 * 出参：Promise<LoadedLLMSettings> - 加载完成后的设置快照
 */
export function ensureLLMSettingsLoaded(options?: { force?: boolean }) {
  return ensureLLMSettingsLoadedInternal(options)
}

/**
 * 函数名：resetLLMSettingsStore
 * 入参：无
 * 功能：将 settingsStore 中与 LLM 相关的字段重置为未加载的初始状态
 * 运行逻辑：直接调用 useSettingsStore.setState 覆盖相关字段
 * 出参：void
 */
export function resetLLMSettingsStore() {
  useSettingsStore.setState({
    providers: [],
    defaultSelection: { provider_id: null, model_id: null, configured: false },
    defaultProviderId: null,
    defaultModelId: null,
    configured: false,
    loaded: false,
  })
}
