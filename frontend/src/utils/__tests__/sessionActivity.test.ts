// 文件功能：hasUnreadActivity 函数的单元测试
// 文件描述：验证 sessionActivity.ts 中未读活动判定逻辑在各类事件序号组合下的正确性
// 核心逻辑：分别覆盖“有未读”“无未读”“乱序不误判”“缺省值按 0 处理”等场景
import { describe, expect, it } from 'vitest'
import { hasUnreadActivity } from '../sessionActivity'

describe('hasUnreadActivity', () => {
  it('当最新事件序号大于已读序号时判定为有未读', () => {
    expect(hasUnreadActivity(10, 5)).toBe(true)
  })

  it('当最新事件序号等于已读序号时判定为无未读', () => {
    expect(hasUnreadActivity(5, 5)).toBe(false)
  })

  it('当最新事件序号小于已读序号时判定为无未读（不会因乱序倒退误判）', () => {
    expect(hasUnreadActivity(3, 5)).toBe(false)
  })

  it('缺省值按 0 处理：从未看过但已有事件，判定为有未读', () => {
    expect(hasUnreadActivity(2, undefined)).toBe(true)
  })

  it('缺省值按 0 处理：均无数据时判定为无未读', () => {
    expect(hasUnreadActivity(undefined, undefined)).toBe(false)
  })
})
