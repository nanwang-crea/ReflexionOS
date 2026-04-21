import { describe, expect, expectTypeOf, it } from 'vitest'
import {
  useSessionSelection,
} from './useSessionSelection'

type Assert<T extends true> = T
type IsExact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false

describe('useSessionSelection helpers', () => {
  it('accepts only preferred selection options as its public input', () => {
    type SessionSelectionOptions = Parameters<typeof useSessionSelection>[0]
    type ExpectedSessionSelectionOptions = {
      preferredProviderId?: string | null
      preferredModelId?: string | null
    }
    type SessionSelectionOptionsExact = Assert<
      IsExact<SessionSelectionOptions, ExpectedSessionSelectionOptions>
    >

    expectTypeOf<SessionSelectionOptions>().toEqualTypeOf<{
      preferredProviderId?: string | null
      preferredModelId?: string | null
    }>()
    const exactMatch: SessionSelectionOptionsExact = true
    expect(exactMatch).toBe(true)
    expect(true).toBe(true)
  })
})
