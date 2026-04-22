import axios from 'axios'
import { llmApi } from '@/services/apiClient'
import { useSettingsStore } from '@/stores/settingsStore'
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

export function createProviderActions(options: CreateProviderActionsOptions) {
  const getErrorMessage = (error: unknown, fallback: string) => {
    if (axios.isAxiosError<{ detail?: string }>(error)) {
      return error.response?.data?.detail || fallback
    }

    return fallback
  }

  return {
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

    async deleteProvider({
      selectedSavedProvider,
      resetDraft,
      confirmDelete,
    }: {
      selectedSavedProvider: ProviderInstance | null
      resetDraft: () => void
      confirmDelete: (provider: ProviderInstance) => boolean
    }) {
      if (!selectedSavedProvider) {
        resetDraft()
        return
      }

      if (!confirmDelete(selectedSavedProvider)) {
        return
      }

      try {
        await options.api.deleteProvider(selectedSavedProvider.id)
        await options.loadSettings()
        options.onSavedMessage('供应商已删除')
      } catch (error: unknown) {
        console.error('Failed to delete provider:', error)
        options.onError(getErrorMessage(error, '删除供应商失败'))
      }
    },

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
      } catch (error: unknown) {
        console.error('Failed to test provider connection:', error)
        options.onTestResult({
          type: 'error',
          message: getErrorMessage(error, '连接测试失败'),
        })
      } finally {
        options.setTesting(false)
      }
    },

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

export function createSettingsPageActions(options: ComposedSettingsPageActionsOptions) {
  return createProviderActions({
    ...options,
    api: llmApi,
    setLLMState: (payload) => useSettingsStore.getState().setLLMState(payload),
  })
}
