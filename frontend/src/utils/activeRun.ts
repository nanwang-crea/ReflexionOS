// 文件功能：从会话状态中解析“当前活跃运行（active run）”的工具函数
// 文件描述：提供根据会话/轮次/运行的规范化状态，推导出当前活跃运行 id 及其状态的纯函数，
//          供多处 UI（如侧边栏、状态徽标）统一判断会话是否正在执行中
// 核心逻辑：优先通过 session.activeTurnId -> turn.activeRunId 链路解析；当该链路因事件到达顺序问题
//          尚未更新时，兜底扫描所有 run 找到状态仍处于活跃集合中的那个
import type { ConversationRunStatus } from '@/types/conversation'

// 视为“活跃”的运行状态集合：已创建/执行中/等待批准/恢复执行中
export const ACTIVE_RUN_STATUSES = new Set<ConversationRunStatus>(['created', 'running', 'waiting_for_approval', 'resuming'])

// 供 resolveActiveRunId 使用的最小会话状态结构（仅取所需字段，便于脱离完整 ConversationState 单独测试/复用）
interface ActiveRunState {
  session: { activeTurnId: string | null } | null
  turnsById: Record<string, { activeRunId: string | null }>
  runsById: Record<string, { status: ConversationRunStatus }>
}

/**
 * 函数名：resolveActiveRunId
 * 入参：
 *   - conversation (ActiveRunState | undefined): 会话的规范化状态（可能为 undefined，表示会话尚未加载）
 * 功能：解析出当前会话中“活跃运行”的 id，若没有活跃运行则返回 null
 * 运行逻辑：
 *   1. 若 conversation 为空，直接返回 null
 *   2. 优先通过 session.activeTurnId 找到对应 turn，再取其 activeRunId
 *   3. 若上述链路未能得到有效 activeRunId（例如 WebSocket 事件乱序导致 session.activeTurnId 滞后），
 *      则兜底遍历 runsById，查找状态处于 ACTIVE_RUN_STATUSES 集合中的运行
 * 出参：string | null - 活跃运行的 id，不存在则为 null
 */
export function resolveActiveRunId(conversation: ActiveRunState | undefined): string | null {
  if (!conversation) {
    return null
  }

  const activeTurnId = conversation.session?.activeTurnId
  if (activeTurnId) {
    const activeRunId = conversation.turnsById[activeTurnId]?.activeRunId
    if (activeRunId) {
      return activeRunId
    }
  }

  // Fallback: when WebSocket events arrive out of order, session.activeTurnId
  // may not yet reflect the server state. Scan all runs for an active one.
  // The backend (resolve_active_run_id_from_conversation) does NOT need this
  // fallback because it reads from the authoritative snapshot directly.
  const activeRunEntry = Object.entries(conversation.runsById).find(([, run]) => ACTIVE_RUN_STATUSES.has(run.status))
  return activeRunEntry?.[0] ?? null
}

/**
 * 函数名：resolveActiveRunStatus
 * 入参：
 *   - conversation (ActiveRunState | undefined): 会话的规范化状态（可能为 undefined）
 * 功能：解析出当前会话中“活跃运行”的状态，若没有活跃运行则返回 null
 * 运行逻辑：先调用 resolveActiveRunId 得到活跃运行 id，再从 runsById 中取出其状态
 * 出参：ConversationRunStatus | null - 活跃运行的状态，不存在则为 null
 */
export function resolveActiveRunStatus(conversation: ActiveRunState | undefined): ConversationRunStatus | null {
  if (!conversation) {
    return null
  }

  const activeRunId = resolveActiveRunId(conversation)
  if (activeRunId) {
    return conversation.runsById[activeRunId]?.status ?? null
  }

  return null
}
