/**
 * 文件功能：视觉（多模态）模型名单常量
 * 文件描述：维护一份已知支持图片/视觉输入的模型 ID 前缀列表，供其他模块判断某个模型是否支持视觉能力
 * 核心逻辑：通过模型 ID 是否以列表中某个前缀开头来做模糊匹配判断（兼容同一模型的不同版本号后缀）
 */
export const VISION_MODELS = [
  'gpt-4o',
  'gpt-4o-mini',
  'gpt-4-turbo',
  'gpt-4-vision-preview',
  'claude-3-opus',
  'claude-3-sonnet',
  'claude-3-haiku',
  'claude-3-5-sonnet',
  'claude-fable-5',
  'gemini-pro-vision',
  'gemini-1.5-pro',
  'gemini-1.5-flash',
]

/**
 * 函数名：supportsVision
 * 入参：
 *   - modelId (string | null | undefined): 待判断的模型 ID，可能为空
 * 功能：判断给定的模型 ID 是否属于支持视觉（图片）输入的模型
 * 运行逻辑：
 *   1. 若 modelId 为空（null/undefined/空字符串），直接返回 false
 *   2. 否则遍历 VISION_MODELS 列表，检查 modelId 是否以列表中任一项为前缀
 * 出参：boolean - true 表示该模型支持视觉输入，false 表示不支持或无法判断
 */
export function supportsVision(modelId: string | null | undefined): boolean {
  if (!modelId) return false
  return VISION_MODELS.some((m) => modelId.startsWith(m))
}
