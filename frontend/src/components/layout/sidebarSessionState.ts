// 派生 sidebar 会话项展示状态的工具模块：根据会话/run/未读信息计算出每个会话应展示的状态徽标，
// 并提供按状态优先级对会话列表排序的函数，供 WorkspaceSidebar 组件使用。
import type { ConversationRunStatus, ConversationState } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import type { SessionSyncHealth } from '@/features/workspace/stores/workspace.store'
import { ACTIVE_RUN_STATUSES, resolveActiveRunStatus } from '@/utils/activeRun'
import { hasUnreadActivity } from '@/utils/sessionActivity'

// sidebar 每个会话项要展示的派生状态。优先级从高到低：
// 同步异常 > 待审批 > 运行中 > 失败(带未读) > 完成(带未读) > 空闲。
// 同步异常排最前：它表示连接层已不实时同步，此时“运行中”等状态可能已过期，
// 不应让用户误以为一切正常或误以为 run 失败。
export type SidebarSessionStatus =
  | 'sync_abnormal'
  | 'waiting_for_approval'
  | 'running'
  | 'failed_with_unread_activity'
  | 'completed_with_unread_activity'
  | 'idle'

export interface SidebarSessionState {
  sessionId: string
  status: SidebarSessionStatus
  // 是否有活跃 run（运行中 / 待审批 / 创建中 / 恢复中）。
  hasActiveRun: boolean
  // 是否有未读活动（最新事件序号超过已读基线）。
  hasUnreadActivity: boolean
  // 用于同优先级内排序的最近活动时间（取会话 updatedAt）。
  lastActivityAt: string
}

// 找出该会话最近一个已结束 run 的终态（失败 / 完成）。
// 仅在没有活跃 run 时用于区分“失败带未读”与“完成带未读”。
function resolveLatestTerminalStatus(
  conversation: ConversationState | undefined,
): Extract<ConversationRunStatus, 'failed' | 'completed' | 'cancelled'> | null {
  if (!conversation) {
    return null
  }

  let latest: { status: 'failed' | 'completed' | 'cancelled'; finishedAt: string } | null = null
  for (const run of Object.values(conversation.runsById)) {
    if (run.status !== 'failed' && run.status !== 'completed' && run.status !== 'cancelled') {
      continue
    }
    const finishedAt = run.finishedAt ?? ''
    if (!latest || finishedAt >= latest.finishedAt) {
      latest = { status: run.status, finishedAt }
    }
  }

  return latest?.status ?? null
}

/**
 * 为单个会话派生 sidebar 展示状态。
 *
 * 真值来源：
 * - 运行状态：优先用已加载的 conversation 快照（精确，可区分运行中/待审批）；
 *   未加载时退回到会话列表的 activeTurnId（粗粒度“有活跃”）。
 * - 未读：用会话列表的 lastEventSeq 与持久化的已读基线比较，
 *   即使该会话快照未加载也能判定。
 */
export function deriveSidebarSessionState(
  session: SessionSummary,
  conversation: ConversationState | undefined,
  lastSeenEventSeq: number | undefined,
  syncHealth?: SessionSyncHealth,
): SidebarSessionState {
  const runStatus = resolveActiveRunStatus(conversation)
  // conversation 已加载时按精确 run 状态判断；未加载时用会话列表的 activeTurnId 兜底。
  const hasActiveRun = runStatus !== null
    ? ACTIVE_RUN_STATUSES.has(runStatus)
    : session.activeTurnId !== null

  const unread = hasUnreadActivity(session.lastEventSeq, lastSeenEventSeq)

  let status: SidebarSessionStatus = 'idle'
  if (syncHealth === 'degraded') {
    // 连接层异常优先于一切运行态展示：避免谎报实时状态。
    status = 'sync_abnormal'
  } else if (runStatus === 'waiting_for_approval') {
    status = 'waiting_for_approval'
  } else if (hasActiveRun) {
    status = 'running'
  } else if (unread) {
    const terminal = resolveLatestTerminalStatus(conversation)
    status = terminal === 'failed' ? 'failed_with_unread_activity' : 'completed_with_unread_activity'
  }

  return {
    sessionId: session.id,
    status,
    hasActiveRun,
    hasUnreadActivity: unread,
    lastActivityAt: session.updatedAt,
  }
}

// sidebar 列表排序优先级：待审批 > 运行中 > 其余。
// 数值越小越靠前。与连接调度优先级共用同一套理解（当前会话另由调用方置顶）。
const STATUS_SORT_WEIGHT: Record<SidebarSessionStatus, number> = {
  sync_abnormal: 0,
  waiting_for_approval: 1,
  running: 2,
  failed_with_unread_activity: 3,
  completed_with_unread_activity: 3,
  idle: 4,
}

/**
 * 按规范对会话状态排序：待审批 → 运行中/恢复中/创建中 → 最近活动时间倒序 → 同优先级内稳定。
 * 返回新数组，不修改入参。indexById 保证同权重时回退到原始顺序（稳定排序）。
 */
export function sortSidebarSessionStates(
  states: SidebarSessionState[],
): SidebarSessionState[] {
  const indexById = new Map(states.map((state, index) => [state.sessionId, index]))

  return states.slice().sort((left, right) => {
    const weightDiff = STATUS_SORT_WEIGHT[left.status] - STATUS_SORT_WEIGHT[right.status]
    if (weightDiff !== 0) {
      return weightDiff
    }

    // 同优先级按最近活动时间倒序。
    if (left.lastActivityAt !== right.lastActivityAt) {
      return left.lastActivityAt > right.lastActivityAt ? -1 : 1
    }

    // 时间相同时按原始顺序稳定排序。
    return (indexById.get(left.sessionId) ?? 0) - (indexById.get(right.sessionId) ?? 0)
  })
}
