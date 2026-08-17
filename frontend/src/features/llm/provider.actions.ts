/**
 * 文件功能：LLM 供应商相关的业务动作（action）封装
 * 文件描述：将"保存/删除供应商""测试连接""保存默认模型选择"等操作从 UI 层的
 *          controller 中抽离出来，以依赖注入的方式接收 api、状态更新回调等依赖，
 *          方便单测替换 mock 实现。
 * 核心逻辑：createProviderActions 是核心工厂函数，统一处理校验、loading 状态切换、
 *          错误信息提取（兼容 axios 错误的 detail/message 字段）；
 *          createSettingsPageActions 是面向设置页面的具体组装，注入真实的 llmApi 和 settingsStore。
 */
import axios from 'axios'
import { llmApi } from './api/llm.api'
import { useSettingsStore } from '@/features/settings/stores/settings.store'
import type { DefaultLLMSelection, ProviderConnectionTestRequest, ProviderConnectionTestResult, ProviderInstance } from '@/types/llm'
import { normalizeProviderDraft, validateProviderDraft } from './providerDraft'

type TestResult = { type: 'success' | 'error'; message: string } | null

interface ProviderApi {
  createProvider: (data: ProviderInstance) => Promise<unknown>
  updateProvider: (providerId: string, data: ProviderInstance) => Promise<unknown>
  deleteProvider: (providerId: string) => Promise<unknown>
  testProvider: (data: ProviderConnectionTestRequest) => Promise<{ data: ProviderConnectionTestResult }>
  setDefaultSelection: (data: { provider_id: string; model_id: string }) => Promise<{ data: DefaultLLMSelection }>
}

interface CreateProviderActionsOptions {
  api: ProviderApi
  loadSettings: (preferredProviderId?: string | null) => Promise<void>
  setLLMState: (payload: { providers: ProviderInstance[]; selection: DefaultLLMSelection }) => void
  setSaving: (saving: boolean) => void
  setSavingDefault: (saving: boolean) => void
  setTesting: (testing: boolean) => void
  onSavedMessage: (message: string | null) => void
  onTestResult: (result: TestResult) => void
  onError: (message: string) => void
}

/**
 * 函数名：createProviderActions
 * 入参：
 *   - options (CreateProviderActionsOptions): 依赖注入配置，包含 api（后端接口）、
 *     loadSettings（刷新设置的方法）、各类 setXxx 状态更新回调、onSavedMessage/
 *     onTestResult/onError 等结果通知回调
 * 功能：创建一组供应商相关的业务动作方法（saveProvider/deleteProvider/
 *      testProviderConnection/saveDefaultSelection），供设置页面的 controller 调用
 * 运行逻辑：内部先定义 getErrorMessage 辅助函数统一提取错误信息（优先取 axios 响应体
 *          中的 message/detail 字段，否则用兜底文案），再返回四个业务方法，
 *          每个方法都遵循"校验 -> 设置 loading -> 调接口 -> 成功/失败回调 -> 结束 loading"的流程
 * 出参：{ saveProvider, deleteProvider, testProviderConnection, saveDefaultSelection } - 动作方法集合
 */
export function createProviderActions(options: CreateProviderActionsOptions) {
  const getErrorMessage = (error: unknown, fallback: string) => {
    if (axios.isAxiosError<{ detail?: string; message?: string }>(error)) {
      return error.response?.data?.message || error.response?.data?.detail || fallback
    }

    return fallback
  }

  return {
    /**
     * 函数名：saveProvider
     * 入参：
     *   - selectedSavedProvider (ProviderInstance | null): 当前已选中的、已保存的供应商
     *     （非 null 表示更新，null 表示新建）
     *   - draftProvider (ProviderInstance): 表单中正在编辑的供应商草稿
     * 功能：校验并保存供应商配置（新建或更新）
     * 运行逻辑：先校验草稿合法性，失败则通过 onError 回调提示并返回；
     *          校验通过后规范化数据（trim 字段等），根据是否有 selectedSavedProvider
     *          调用 updateProvider 或 createProvider，成功后重新加载设置并提示保存成功
     * 出参：Promise<void>
     */
    async saveProvider({
      selectedSavedProvider,
      draftProvider,
    }: {
      selectedSavedProvider: ProviderInstance | null
      draftProvider: ProviderInstance
    }) {
      const validationError = validateProviderDraft(draftProvider)
      if (validationError) {
        options.onError(validationError)
        return
      }

      const payload = normalizeProviderDraft(draftProvider)
      options.setSaving(true)
      options.onSavedMessage(null)

      try {
        if (selectedSavedProvider) {
          await options.api.updateProvider(selectedSavedProvider.id, payload)
        } else {
          await options.api.createProvider(payload)
        }

        await options.loadSettings(payload.id)
        options.onSavedMessage('供应商已保存')
      } catch (error: unknown) {
        console.error('Failed to save provider:', error)
        options.onError(getErrorMessage(error, '保存供应商失败'))
      } finally {
        options.setSaving(false)
      }
    },

    /**
     * 函数名：deleteProvider
     * 入参：
     *   - selectedSavedProvider (ProviderInstance | null): 待删除的供应商，null 表示无选中（直接重置草稿）
     *   - resetDraft (() => void): 重置表单草稿的回调
     *   - confirmDelete ((provider) => Promise<boolean>): 删除前的二次确认回调
     * 功能：删除指定供应商，并在删除前进行用户确认
     * 运行逻辑：无选中供应商时直接重置草稿；否则先调用 confirmDelete 弹窗确认，
     *          确认后调用接口删除，成功后强制刷新设置（传 null 使 loadSettings 不指定首选项）
     * 出参：Promise<void>
     */
    async deleteProvider({
      selectedSavedProvider,
      resetDraft,
      confirmDelete,
    }: {
      selectedSavedProvider: ProviderInstance | null
      resetDraft: () => void
      confirmDelete: (provider: ProviderInstance) => Promise<boolean>
    }) {
      if (!selectedSavedProvider) {
        resetDraft()
        return
      }

      if (!(await confirmDelete(selectedSavedProvider))) {
        return
      }

      try {
        await options.api.deleteProvider(selectedSavedProvider.id)
        await options.loadSettings(null)
        options.onSavedMessage('供应商已删除')
      } catch (error: unknown) {
        console.error('Failed to delete provider:', error)
        options.onError(getErrorMessage(error, '删除供应商失败'))
      }
    },

    /**
     * 函数名：testProviderConnection
     * 入参：
     *   - draftProvider (ProviderInstance): 待测试连接的供应商草稿
     * 功能：校验草稿后调用后端接口测试与该供应商的连接是否可用
     * 运行逻辑：先校验草稿合法性；确定用于测试的模型 id（优先取 default_model_id，
     *          否则取第一个模型），若没有可用模型则提示错误；调用 testProvider 接口，
     *          成功后返回探测到的能力信息（如是否支持视觉），供调用方更新草稿
     * 出参：Promise<{ modelId, supports_vision } | null> - 测试成功时返回探测到的模型能力，
     *      失败或校验不通过时返回 null
     */
    async testProviderConnection(draftProvider: ProviderInstance) {
      const validationError = validateProviderDraft(draftProvider)
      if (validationError) {
        options.onTestResult({ type: 'error', message: validationError })
        return
      }

      const payload = normalizeProviderDraft(draftProvider)
      const modelId = payload.default_model_id || payload.models[0]?.id || null
      if (!modelId) {
        options.onTestResult({ type: 'error', message: '请先至少配置一个模型' })
        return
      }

      options.setTesting(true)
      options.onTestResult(null)

      try {
        const response = await options.api.testProvider({
          provider: payload,
          model_id: modelId,
        })
        options.onTestResult({
          type: 'success',
          message: `${response.data.message}，模型：${response.data.model}`,
        })

        // Return the updated capability info so controller can update draft
        return {
          modelId: response.data.model_id,
          supports_vision: response.data.supports_vision,
        }
      } catch (error: unknown) {
        console.error('Failed to test provider connection:', error)
        options.onTestResult({
          type: 'error',
          message: getErrorMessage(error, '连接测试失败'),
        })
        return null
      } finally {
        options.setTesting(false)
      }
    },

    /**
     * 函数名：saveDefaultSelection
     * 入参：
     *   - defaultSelection (DefaultLLMSelection): 待保存的默认供应商/模型选择
     *   - providers (ProviderInstance[]): 当前完整的供应商列表（用于回写 store）
     * 功能：保存用户设置的默认供应商与默认模型
     * 运行逻辑：校验 provider_id 和 model_id 均已选择，否则提示错误；
     *          调用 setDefaultSelection 接口保存，成功后用返回结果更新 store 中的 LLM 状态
     * 出参：Promise<DefaultLLMSelection | null> - 保存成功返回最新选择，否则返回 null
     */
    async saveDefaultSelection({
      defaultSelection,
      providers,
    }: {
      defaultSelection: DefaultLLMSelection
      providers: ProviderInstance[]
    }) {
      if (!defaultSelection.provider_id || !defaultSelection.model_id) {
        options.onError('请选择默认供应商和默认模型')
        return
      }

      options.setSavingDefault(true)
      options.onSavedMessage(null)

      try {
        const response = await options.api.setDefaultSelection({
          provider_id: defaultSelection.provider_id,
          model_id: defaultSelection.model_id,
        })

        options.setLLMState({
          providers,
          selection: response.data,
        })
        options.onSavedMessage('默认模型已保存')

        return response.data
      } catch (error: unknown) {
        console.error('Failed to save default selection:', error)
        options.onError(getErrorMessage(error, '保存默认模型失败'))
        return null
      } finally {
        options.setSavingDefault(false)
      }
    },
  }
}

type ComposedSettingsPageActionsOptions = Omit<CreateProviderActionsOptions, 'api' | 'setLLMState'>

/**
 * 函数名：createSettingsPageActions
 * 入参：
 *   - options (ComposedSettingsPageActionsOptions): 除 api/setLLMState 之外的其余依赖配置
 *     （这两项由本函数固定注入真实实现，调用方无需关心）
 * 功能：面向设置页面的具体组装函数，注入真实的 llmApi 和 settingsStore 更新逻辑
 * 运行逻辑：调用 createProviderActions，补全 api 为 llmApi、setLLMState 为写入
 *          useSettingsStore 的方法，其余依赖直接透传调用方传入的 options
 * 出参：ReturnType<typeof createProviderActions> - 组装好的动作方法集合
 */
export function createSettingsPageActions(options: ComposedSettingsPageActionsOptions) {
  return createProviderActions({
    ...options,
    api: llmApi,
    setLLMState: (payload) => useSettingsStore.getState().setLLMState(payload),
  })
}
