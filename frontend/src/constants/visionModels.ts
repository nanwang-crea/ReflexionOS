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

export function supportsVision(modelId: string | null | undefined): boolean {
  if (!modelId) return false
  return VISION_MODELS.some((m) => modelId.startsWith(m))
}
