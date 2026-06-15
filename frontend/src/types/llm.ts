export type ProviderType = 'openai_compatible' | 'anthropic' | 'ollama'

export interface ProviderModel {
  id: string
  display_name: string
  model_name: string
  enabled: boolean
  // Model capabilities (null = not probed, true/false = known)
  supports_vision?: boolean | null
  supports_tools?: boolean | null
  supports_reasoning?: boolean | null
}

export interface ProviderInstance {
  id: string
  name: string
  provider_type: ProviderType
  api_key?: string
  base_url?: string
  models: ProviderModel[]
  default_model_id?: string
  enabled: boolean
}

export interface DefaultLLMSelection {
  provider_id: string | null
  model_id: string | null
  configured: boolean
}

export interface ProviderConnectionTestRequest {
  provider: ProviderInstance
  model_id?: string | null
}

export interface ProviderConnectionTestResult {
  success: boolean
  provider_id: string
  provider_type: ProviderType
  model_id: string
  model: string
  message: string
  supports_vision?: boolean | null
}
