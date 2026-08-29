// isConversationBusy 的单测：验证在不同 run 状态组合下，能否正确判定会话是否处于“忙碌”态。
import { describe, expect, it } from 'vitest'
import { isConversationBusy } from '../sidebarBusy'

describe('isConversationBusy', () => {
  // 参数：无。
  // 验证：conversation 为 undefined（会话快照未加载）时返回 false。
  it('returns false when there is no conversation state', () => {
    expect(isConversationBusy(undefined)).toBe(false)
  })

  // 参数：无。
  // 验证：活跃 run 状态为 running 时返回 true。
  it('returns true when the active run is still running', () => {
    expect(isConversationBusy({
      session: { activeTurnId: 'turn-1' },
      turnsById: { 'turn-1': { activeRunId: 'run-1' } },
      runsById: { 'run-1': { status: 'running' } },
    })).toBe(true)
  })

  // 参数：无。
  // 验证：活跃 run 状态为 waiting_for_approval 或 resuming 时均返回 true（属于“活跃”状态集合）。
  it('returns true when the active run is waiting for approval or resuming', () => {
    expect(isConversationBusy({
      session: { activeTurnId: 'turn-1' },
      turnsById: { 'turn-1': { activeRunId: 'run-1' } },
      runsById: { 'run-1': { status: 'waiting_for_approval' } },
    })).toBe(true)

    expect(isConversationBusy({
      session: { activeTurnId: 'turn-1' },
      turnsById: { 'turn-1': { activeRunId: 'run-1' } },
      runsById: { 'run-1': { status: 'resuming' } },
    })).toBe(true)
  })

  // 参数：无。
  // 验证：run 状态为 completed（已结束）时返回 false，不属于“忙碌”态。
  it('returns false when there is no active running or created run', () => {
    expect(isConversationBusy({
      session: { activeTurnId: 'turn-1' },
      turnsById: { 'turn-1': { activeRunId: 'run-1' } },
      runsById: { 'run-1': { status: 'completed' } },
    })).toBe(false)
  })
})
