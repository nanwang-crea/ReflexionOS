import { useState, useEffect } from 'react'
import { llmApi } from '@/services/apiClient'
import { useSettingsStore } from '@/stores/settingsStore'
import { LLMProvider } from '@/types/llm'

const DEFAULT_OPENAI_MODEL = 'qwen3.6-plus'

export default function SettingsPage() {
  const { setLLMConfig, configured, setConfigured } = useSettingsStore()
  const [providers, setProviders] = useState<LLMProvider[]>([])
  const [formData, setFormData] = useState({
    provider: 'openai',
    model: DEFAULT_OPENAI_MODEL,
    api_key: '',
    base_url: '',
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    loadProviders()
    loadConfig()
  }, [])

  const loadProviders = async () => {
    try {
      const response = await llmApi.getProviders()
      setProviders(response.data)
    } catch (error) {
      console.error('Failed to load providers:', error)
    }
  }

  const loadConfig = async () => {
    try {
      const response = await llmApi.getConfig()
      if (response.data.provider || response.data.model || response.data.base_url) {
        setFormData({
          provider: response.data.provider || 'openai',
          model: response.data.model || DEFAULT_OPENAI_MODEL,
          api_key: '',
          base_url: response.data.base_url || '',
        })
      }

      setConfigured(Boolean(response.data.configured))
    } catch (error) {
      console.error('Failed to load config:', error)
    }
  }

  const handleSave = async () => {
    const model = formData.model.trim()
    if (!model) {
      alert('Model is required')
      return
    }

    const payload = {
      provider: formData.provider,
      model,
      api_key: formData.api_key.trim() || undefined,
      base_url: formData.base_url.trim() || undefined,
    }

    setSaving(true)
    try {
      const response = await llmApi.setConfig(payload)

      setFormData({
        provider: response.data.provider || payload.provider,
        model: response.data.model || payload.model,
        api_key: '',
        base_url: response.data.base_url || payload.base_url || '',
      })

      setLLMConfig({
        provider: (response.data.provider || payload.provider) as any,
        model: response.data.model || payload.model,
        api_key: payload.api_key,
        base_url: response.data.base_url || payload.base_url,
      })
      setConfigured(Boolean(response.data.configured))
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (error) {
      console.error('Failed to save config:', error)
      alert('Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  const selectedProvider = providers.find((p) => p.id === formData.provider)

  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Settings</h2>

      <div className="bg-white rounded-lg border border-gray-200 p-6 max-w-2xl">
        <h3 className="text-lg font-semibold mb-4">LLM Configuration</h3>

        {configured && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700">
            LLM is configured and ready to use.
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Provider
            </label>
            <select
              value={formData.provider}
              onChange={(e) => {
                const provider = providers.find((p) => p.id === e.target.value)
                setFormData({
                  ...formData,
                  provider: e.target.value,
                  model: provider?.models[0] || '',
                })
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
            >
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                  {provider.status === 'coming_soon' && ' (Coming Soon)'}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Model
            </label>
            <input
              type="text"
              list="llm-model-suggestions"
              value={formData.model}
              onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              placeholder="e.g. qwen3.6-plus"
            />
            <datalist id="llm-model-suggestions">
              {selectedProvider?.models.map((model) => (
                <option key={model} value={model} />
              ))}
            </datalist>
            <p className="mt-1 text-sm text-gray-500">
              You can choose a suggested model or type any OpenAI-compatible model name manually.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              API Key
            </label>
            <input
              type="password"
              value={formData.api_key}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              placeholder="sk-..."
            />
            <p className="mt-1 text-sm text-gray-500">
              Your API key is stored locally and never sent to our servers.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Base URL (Optional)
            </label>
            <input
              type="text"
              value={formData.base_url}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              placeholder="https://api.openai.com/v1"
            />
            <p className="mt-1 text-sm text-gray-500">
              For OpenAI-compatible APIs (e.g., Azure OpenAI, local LLMs).
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-4">
          <button
            onClick={handleSave}
            disabled={saving}
            className={`px-4 py-2 rounded-lg ${
              saving
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
          {saved && (
            <span className="text-green-600">Configuration saved!</span>
          )}
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-6 max-w-2xl mt-6">
        <h3 className="text-lg font-semibold mb-4">About</h3>
        <p className="text-gray-600">
          ReflexionOS is an AI-powered coding agent that runs locally on your machine.
          It can read, write, and modify files, execute shell commands, and help you
          accomplish coding tasks autonomously.
        </p>
        <p className="text-gray-500 text-sm mt-2">Version 0.1.0</p>
      </div>
    </div>
  )
}
