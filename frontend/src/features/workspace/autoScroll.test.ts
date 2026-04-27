import { describe, expect, it } from 'vitest'
import { AUTO_SCROLL_FOLLOW_THRESHOLD_PX, shouldFollowTranscript } from './autoScroll'

describe('shouldFollowTranscript', () => {
  it('returns true when the viewport is already near the bottom', () => {
    expect(
      shouldFollowTranscript({
        scrollTop: 920,
        clientHeight: 280,
        scrollHeight: 1240,
      })
    ).toBe(true)
  })

  it('returns false when the user has scrolled away from the bottom', () => {
    expect(
      shouldFollowTranscript({
        scrollTop: 400,
        clientHeight: 280,
        scrollHeight: 1240,
      })
    ).toBe(false)
  })

  it('uses a small threshold so tiny offsets still follow the stream', () => {
    expect(
      shouldFollowTranscript({
        scrollTop: 1240 - 280 - AUTO_SCROLL_FOLLOW_THRESHOLD_PX + 1,
        clientHeight: 280,
        scrollHeight: 1240,
      })
    ).toBe(true)
  })
})
