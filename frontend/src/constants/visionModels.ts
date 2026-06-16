/**
 * visionModels centralizes frontend-side image capability detection.
 *
 * It keeps a conservative fallback prefix list for common public model ids, but
 * prefers the per-model `supports_vision` capability returned by provider settings
 * when that signal is available.
 */
import type { ProviderModel } from '@/types/llm'

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
 * Checks image support by model id using the built-in fallback prefix list.
 */
export function supportsVision(modelId: string | null | undefined): boolean {
  if (!modelId) return false
  return VISION_MODELS.some((m) => modelId.startsWith(m))
}

/**
 * Resolves whether a configured provider model supports image input.
 *
 * It prefers the server-probed `supports_vision` capability, and only falls back
 * to prefix matching when the provider has not been probed yet.
 */
export function supportsVisionModel(model: Pick<ProviderModel, 'id' | 'model_name' | 'supports_vision'> | null | undefined): boolean {
  if (!model) {
    return false
  }
  if (typeof model.supports_vision === 'boolean') {
    return model.supports_vision
  }
  return supportsVision(model.id) || supportsVision(model.model_name)
}
