import { describe, expect, it } from 'vitest'
import { getReceiptFinalizeDelay, MIN_RECEIPT_VISIBLE_MS } from './receiptTiming'

describe('getReceiptFinalizeDelay', () => {
  it('returns zero when receipt has been visible long enough', () => {
    expect(getReceiptFinalizeDelay(100, 100 + MIN_RECEIPT_VISIBLE_MS)).toBe(0)
  })

  it('returns remaining delay when receipt would disappear too quickly', () => {
    expect(getReceiptFinalizeDelay(100, 150, 120)).toBe(70)
  })

  it('returns zero when receipt was never shown', () => {
    expect(getReceiptFinalizeDelay(null, 200)).toBe(0)
  })
})
