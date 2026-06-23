import { describe, expect, it } from 'vitest'
import type { ConversationRunStatus, ConversationState } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import {
  deriveSidebarSessionState,
  sortSidebarSessionStates,
  type SidebarSessionState,
} from '../sidebarSessionState'

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
  it('待审批优先于其他状态', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'waiting_for_approval'),
      0,
    )
    expect(state.status).toBe('waiting_for_approval')
    expect(state.hasActiveRun).toBe(true)
  })

  it('运行中标记为 running', () => {
    const state = deriveSidebarSessionState(
      buildSession(),
      buildConversation('run-1', 'running'),
      0,
    )
    expect(state.status).toBe('running')
  })

  it('无活跃 run 但有未读且最近一次失败：标记为失败带未读', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 9, activeTurnId: null }),
      buildConversation('run-1', 'failed', '2026-06-22T10:01:00Z'),
      3,
    )
    expect(state.hasActiveRun).toBe(false)
    expect(state.status).toBe('failed_with_unread_activity')
  })

  it('无活跃 run 但有未读且最近一次完成：标记为完成带未读', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 9 }),
      buildConversation('run-1', 'completed', '2026-06-22T10:01:00Z'),
      3,
    )
    expect(state.status).toBe('completed_with_unread_activity')
  })

  it('无活跃、无未读：标记为空闲', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'completed', '2026-06-22T10:01:00Z'),
      5,
    )
    expect(state.status).toBe('idle')
    expect(state.hasUnreadActivity).toBe(false)
  })

  it('快照未加载时用会话列表 activeTurnId 兜底判定活跃', () => {
    const state = deriveSidebarSessionState(
      buildSession({ activeTurnId: 'turn-1', lastEventSeq: 2 }),
      undefined,
      0,
    )
    expect(state.hasActiveRun).toBe(true)
    expect(state.status).toBe('running')
  })

  it('同步异常优先于运行中：避免谎报实时状态', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'running'),
      0,
      'degraded',
    )
    expect(state.status).toBe('sync_abnormal')
  })

  it('同步异常优先于待审批', () => {
    const state = deriveSidebarSessionState(
      buildSession({ lastEventSeq: 5 }),
      buildConversation('run-1', 'waiting_for_approval'),
      0,
      'degraded',
    )
    expect(state.status).toBe('sync_abnormal')
  })

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

  it('同步异常排在所有状态最前', () => {
    const sorted = sortSidebarSessionStates([
      s('running', 'running', '2026-06-22T11:00:00Z'),
      s('approval', 'waiting_for_approval', '2026-06-22T11:00:00Z'),
      s('abnormal', 'sync_abnormal', '2026-06-22T08:00:00Z'),
    ])
    expect(sorted[0].sessionId).toBe('abnormal')
  })
})
