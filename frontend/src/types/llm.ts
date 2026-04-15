export interface LLMConfig {
  provider: 'openai' | 'claude' | 'ollama'
  model: string
  api_key?: string
  base_url?: string
  temperature?: number
  max_tokens?: number
}

export interface LLMProvider {
  id: string
  name: string
  models: string[]
  status?: string
}
