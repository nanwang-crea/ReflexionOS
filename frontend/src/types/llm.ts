// 文件功能：LLM 提供方（provider）与模型相关类型定义
// 文件描述：定义 LLM 服务提供方实例、其下模型列表、默认选择、连接测试请求/结果等类型，
//          供前端“模型设置”页面配置和测试各类 LLM 提供方使用
// 核心逻辑：一个 ProviderInstance（如某个 OpenAI 兼容服务/Anthropic/Ollama 的接入配置）下可含多个
//          ProviderModel；DefaultLLMSelection 记录全局默认使用哪个提供方+模型
// LLM 提供方类型：openai_compatible(OpenAI 兼容接口) / anthropic(Anthropic 官方接口) / ollama(本地 Ollama)
export type ProviderType = 'openai_compatible' | 'anthropic' | 'ollama'

// 提供方下的单个模型配置
export interface ProviderModel {
  id: string
  display_name: string // 展示用名称
  model_name: string // 调用接口时实际使用的模型标识
  enabled: boolean // 是否启用（禁用后不出现在可选模型列表中）
  // Model capabilities (null = not probed, true/false = known)
  // 模型能力探测结果：null 表示尚未探测，true/false 表示已知支持/不支持
  supports_vision?: boolean | null
  supports_tools?: boolean | null
  supports_reasoning?: boolean | null
}

// LLM 提供方实例：一个具体的服务接入配置（如某个 API Key + Base URL 组合）
export interface ProviderInstance {
  id: string
  name: string // 用户自定义的提供方名称
  provider_type: ProviderType
  api_key?: string
  base_url?: string // 自定义接口地址（如私有部署/OpenAI 兼容代理地址）
  models: ProviderModel[]
  default_model_id?: string // 该提供方下默认使用的模型 id
  enabled: boolean // 是否启用该提供方
}

// 全局默认 LLM 选择：记录当前默认使用哪个提供方+模型
export interface DefaultLLMSelection {
  provider_id: string | null
  model_id: string | null
  configured: boolean // 是否已完成配置（provider_id/model_id 均非空时一般为 true）
}

// 提供方连接测试请求：携带完整提供方配置及可选的指定模型，用于测试连通性
export interface ProviderConnectionTestRequest {
  provider: ProviderInstance
  model_id?: string | null // 指定测试使用的模型；未指定时通常使用默认模型
}

// 提供方连接测试结果
export interface ProviderConnectionTestResult {
  success: boolean
  provider_id: string
  provider_type: ProviderType
  model_id: string
  model: string // 实际测试所用的模型标识
  message: string // 测试结果说明（成功提示或失败原因）
  supports_vision?: boolean | null // 测试过程中探测到的视觉能力支持情况
}
