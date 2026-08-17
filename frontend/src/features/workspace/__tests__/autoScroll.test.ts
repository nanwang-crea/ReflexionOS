/**
 * 文件功能：autoScroll.ts 单元测试
 * 文件描述：验证 shouldFollowTranscript 在不同滚动位置下是否正确判断应否自动跟随滚动到底部，
 *           以及阈值常量 AUTO_SCROLL_FOLLOW_THRESHOLD_PX 的边界行为。
 * 核心逻辑：分别构造“已在底部附近”“已远离底部”以及刚好卡在阈值边界两侧的滚动位置进行断言。
 */
import { describe, expect, it } from 'vitest'
import { AUTO_SCROLL_FOLLOW_THRESHOLD_PX, shouldFollowTranscript } from '../autoScroll'

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

  it('uses a 100px threshold so nearby streaming output still follows', () => {
    expect(AUTO_SCROLL_FOLLOW_THRESHOLD_PX).toBe(100)
    expect(
      shouldFollowTranscript({
        scrollTop: 1240 - 280 - AUTO_SCROLL_FOLLOW_THRESHOLD_PX + 1,
        clientHeight: 280,
        scrollHeight: 1240,
      })
    ).toBe(true)
  })

  it('returns false immediately when the viewport is more than 100px from the bottom', () => {
    expect(
      shouldFollowTranscript({
        scrollTop: 1240 - 280 - AUTO_SCROLL_FOLLOW_THRESHOLD_PX - 1,
        clientHeight: 280,
        scrollHeight: 1240,
      })
    ).toBe(false)
  })
})
