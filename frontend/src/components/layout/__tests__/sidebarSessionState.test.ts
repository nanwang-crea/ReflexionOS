// sidebarSessionState 模块的单测：覆盖 deriveSidebarSessionState 的状态优先级判定
// （同步异常 > 待审批 > 运行中 > 失败/完成带未读 > 空闲）以及 sortSidebarSessionStates 的排序规则。
import { describe, expect, it } from 'vitest'
import type { ConversationRunStatus, ConversationState } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import {
  deriveSidebarSessionState,
  sortSidebarSessionStates,
  type SidebarSessionState,
} from '../sidebarSessionState'

// 参数：overrides - 需要覆盖的 SessionSummary 字段。
// 作用：构造一个带默认值的最小 SessionSummary 测试夹具，未传的字段使用合理默认值填充。
// 返回：完整的 SessionSummary 对象。
function buildSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: 'session-1',
    projectId: 'project-1',
    title: '会话',
    lastEventSeq: 0,
    activeTurnId: null,
    createdAt: '2026-06-22T10:00:00Z',
    updatedAt: '2026-06-22T10:00:00Z',
    ...overrides,
  }
}

// 构造一个最小 conversation 状态：一个 turn 指向一个 run。
// 参数：runId - run 的 id；status - run 的运行状态；finishedAt - 结束时间（未结束传 null）。
// 作用：拼装出 deriveSidebarSessionState 需要的最小 ConversationState 结构（仅含一个 turn/一个 run）。
// 返回：完整的 ConversationState 测试夹具。
function buildConversation(
  runId: string,
  status: ConversationRunStatus,
  finishedAt: string | null = null,
): ConversationState {
  return {
    sessionId: 'session-1',
    lastEventSeq: 0,
    session: { activeTurnId: 'turn-1' } as ConversationState['session'],
    turnOrder: ['turn-1'],
    turnsById: { 'turn-1': { activeRunId: runId } } as unknown as ConversationState['turnsById'],
    runsById: {
      [runId]: {
        id: runId,
        sessionId: 'session-1',
        turnId: 'turn-1',
        attemptIndex: 1,
        status,
        providerId: null,
        modelId: null,
        workspaceRef: null,
        startedAt: null,
        finishedAt,
        errorCode: null,
        errorMessage: null,
      },
    },
    messageOrder: [],
    messagesById: {},
    hasMore: false,
    nextBeforeTurnId: null,
  }
}

describe('deriveSidebarSessionState', () => {
  // 参数：无。
  // 验证：run 状态为 waiting_for_approval 时，派生状态优先判定为 waiting_for_approval（且 hasActiveRun 为 true）。
  it('待审批优先于其他状态', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'waiting_for_approval'),
      0,
    )
    expect(state.status).toBe('waiting_for_approval')
    expect(state.hasActiveRun).toBe(true)
  })

  // 参数：无。
  // 验证：run 状态为 running 时，派生状态为 running。
  it('运行中标记为 running', () => {
    const state = deriveSidebarSessionState(
      buildSession(),
      buildConversation('run-1', 'running'),
      0,
    )
    expect(state.status).toBe('running')
  })

  // 参数：无。
  // 验证：无活跃 run（activeTurnId 为 null）、有未读事件、且最近一次结束的 run 状态是 failed 时，
  // 派生状态为 failed_with_unread_activity。
  it('无活跃 run 但有未读且最近一次失败：标记为失败带未读', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 9, activeTurnId: null }),
      buildConversation('run-1', 'failed', '2026-06-22T10:01:00Z'),
      3,
    )
    expect(state.hasActiveRun).toBe(false)
    expect(state.status).toBe('failed_with_unread_activity')
  })

  // 参数：无。
  // 验证：无活跃 run、有未读事件、且最近一次结束的 run 状态是 completed 时，
  // 派生状态为 completed_with_unread_activity。
  it('无活跃 run 但有未读且最近一次完成：标记为完成带未读', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 9 }),
      buildConversation('run-1', 'completed', '2026-06-22T10:01:00Z'),
      3,
    )
    expect(state.status).toBe('completed_with_unread_activity')
  })

  // 参数：无。
  // 验证：无活跃 run、且已读事件序号等于最新事件序号（无未读）时，派生状态为 idle，hasUnreadActivity 为 false。
  it('无活跃、无未读：标记为空闲', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'completed', '2026-06-22T10:01:00Z'),
      5,
    )
    expect(state.status).toBe('idle')
    expect(state.hasUnreadActivity).toBe(false)
  })

  // 参数：无。
  // 验证：conversation 快照未加载（undefined）时，退回到 session.activeTurnId 判断是否活跃；
  // 有 activeTurnId 时应判定 hasActiveRun 为 true，状态为 running。
  it('快照未加载时用会话列表 activeTurnId 兜底判定活跃', () => {
    const state = deriveSidebarSessionState(
      buildSession({ activeTurnId: 'turn-1', lastEventSeq: 2 }),
      undefined,
      0,
    )
    expect(state.hasActiveRun).toBe(true)
    expect(state.status).toBe('running')
  })

  // 参数：无。
  // 验证：syncHealth 为 'degraded' 时，即使 run 状态为 running，派生状态也优先判定为 sync_abnormal。
  it('同步异常优先于运行中：避免谎报实时状态', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'running'),
      0,
      'degraded',
    )
    expect(state.status).toBe('sync_abnormal')
  })

  // 参数：无。
  // 验证：syncHealth 为 'degraded' 时，即使 run 状态为 waiting_for_approval，也优先判定为 sync_abnormal。
  it('同步异常优先于待审批', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'waiting_for_approval'),
      0,
      'degraded',
    )
    expect(state.status).toBe('sync_abnormal')
  })

  // 参数：无。
  // 验证：不传 syncHealth（undefined）时不影响原有的状态判定逻辑，run 状态为 running 时仍判定为 running。
  it('未传同步健康时维持原有状态判定', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'running'),
      0,
      undefined,
    )
    expect(state.status).toBe('running')
  })
})

describe('sortSidebarSessionStates', () => {
  // 参数：sessionId - 会话 id；status - 会话状态；lastActivityAt - 最近活动时间。
  // 作用：构造一个最小 SidebarSessionState 测试夹具，hasActiveRun/hasUnreadActivity 根据 status 自动推导。
  // 返回：SidebarSessionState 对象。
  function s(
    sessionId: string,
    status: SidebarSessionState['status'],
    lastActivityAt: string,
  ): SidebarSessionState {
    return {
      sessionId,
      status,
      hasActiveRun: status === 'running' || status === 'waiting_for_approval',
      hasUnreadActivity: status.includes('unread'),
      lastActivityAt,
    }
  }

  // 参数：无。
  // 验证：排序结果依次是 待审批 → 运行中（新活动在前）→ 空闲；同优先级内按 lastActivityAt 倒序排列。
  it('按 待审批 → 运行中 → 其余 排序，同优先级内按活动时间倒序', () => {
    const sorted = sortSidebarSessionStates([
      s('idle', 'idle', '2026-06-22T10:00:00Z'),
      s('running-old', 'running', '2026-06-22T10:00:00Z'),
      s('running-new', 'running', '2026-06-22T11:00:00Z'),
      s('approval', 'waiting_for_approval', '2026-06-22T09:00:00Z'),
    ])
    expect(sorted.map((entry) => entry.sessionId)).toEqual([
      'approval',
      'running-new',
      'running-old',
      'idle',
    ])
  })

  // 参数：无。
  // 验证：即使 sync_abnormal 状态的活动时间最早，排序结果中它仍排在所有其他状态最前面。
  it('同步异常排在所有状态最前', () => {
    const sorted = sortSidebarSessionStates([
      s('running', 'running', '2026-06-22T11:00:00Z'),
      s('approval', 'waiting_for_approval', '2026-06-22T11:00:00Z'),
      s('abnormal', 'sync_abnormal', '2026-06-22T08:00:00Z'),
    ])
    expect(sorted[0].sessionId).toBe('abnormal')
  })
})
