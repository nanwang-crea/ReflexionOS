/**
 * visionModels tests guard the image-capability detection used by the chat input.
 *
 * They verify that probed provider capabilities override fallback heuristics and
 * that the legacy prefix list still works when the provider has not been probed.
 */
import { describe, expect, it } from 'vitest'
import { supportsVision, supportsVisionModel } from '../visionModels'

describe('visionModels', () => {
  it('keeps the prefix-based fallback for common public model ids', () => {
    expect(supportsVision('gpt-4o')).toBe(true)
    expect(supportsVision('claude-3-5-sonnet-20241022')).toBe(true)
    expect(supportsVision('text-only-model')).toBe(false)
  })

  it('prefers the probed supports_vision capability when available', () => {
    expect(supportsVisionModel({
      id: 'custom-model',
      model_name: 'custom-model',
      supports_vision: true,
    })).toBe(true)

    expect(supportsVisionModel({
      id: 'gpt-4o',
      model_name: 'gpt-4o',
      supports_vision: false,
    })).toBe(false)
  })

  it('falls back to id or model_name prefix matching when capability is not probed', () => {
    expect(supportsVisionModel({
      id: 'custom-alias',
      model_name: 'gemini-1.5-pro-latest',
      supports_vision: null,
    })).toBe(true)
  })
})
