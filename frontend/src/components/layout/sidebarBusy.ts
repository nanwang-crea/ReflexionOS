// 判断某个会话当前是否处于“忙碌”（有活跃 run）状态的工具函数，供 WorkspaceSidebar 用于禁用相关操作按钮。
import { ACTIVE_RUN_STATUSES, resolveActiveRunStatus } from '@/utils/activeRun'
import type { ConversationRunStatus } from '@/types/conversation'

type BusyConversationState = {
  session: { activeTurnId: string | null } | null
  turnsById: Record<string, { activeRunId: string | null }>
  runsById: Record<string, { status: ConversationRunStatus }>
}

// 参数：conversation - 会话状态快照（可能未加载，为 undefined）。
// 作用：从会话状态中解析出当前活跃 run 的状态，并判断该状态是否属于“活跃”集合（运行中/待审批等）。
// 返回：true 表示该会话正忙（存在活跃 run），false 表示空闲或会话未加载。
export function isConversationBusy(conversation: BusyConversationState | undefined): boolean {
  const status = resolveActiveRunStatus(conversation)
  return status ? ACTIVE_RUN_STATUSES.has(status) : false
}
