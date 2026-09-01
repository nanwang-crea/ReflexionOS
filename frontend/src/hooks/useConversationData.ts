// 文件功能：聚合当前会话的消息列表、运行状态、计划信息与分页游标
// 文件描述：从会话 store 中取出指定会话的原始数据，派生出 UI 直接可用的消息数组、是否正在运行、
// 关联计划、是否还有更多历史消息等信息
// 核心逻辑：通过 useMemo 缓存消息列表和运行状态的派生计算，避免每次渲染都重新遍历/查找
import { useMemo } from 'react'
import { useConversationStore } from '@/features/conversation/stores/conversation.store'
import type { ConversationMessage } from '@/types/conversation'
import { ACTIVE_RUN_STATUSES, resolveActiveRunId } from '@/utils/activeRun'

// 函数名：useConversationData
// 入参：
//   - currentSessionId (string | null): 当前会话 ID，为 null 时表示没有选中会话
// 功能：为会话视图提供渲染所需的全部派生数据（消息、运行中状态、计划、分页信息）
// 运行逻辑：
//   1. 订阅 store 中该会话的原始 conversation 数据（messagesById/messageOrder/runsById 等）
//   2. 用 useMemo 把 messageOrder 映射为按顺序排列、过滤掉空值的 ConversationMessage 数组
//   3. 用 useMemo 结合 resolveActiveRunId 找到当前活跃的运行，并判断其状态是否属于“运行中”集合
//   4. 单独订阅该会话关联的 plan 数据
//   5. 从 conversation 中读取 hasMore（是否还有更早消息）和 nextBeforeTurnId（下一页游标）
// 出参：{ messages, isRunning, plan, hasMore, oldestLoadedTurnId } - 会话视图所需的聚合数据
export function useConversationData(currentSessionId: string | null) {
  const conversation = useConversationStore((state) => {
    if (!currentSessionId) {
      return undefined
    }

    return state.conversationsBySessionId[currentSessionId]
  })

  const messages = useMemo(() => {
    if (!conversation) {
      return [] as ConversationMessage[]
    }

    return conversation.messageOrder
      .map((messageId) => conversation.messagesById[messageId])
      .filter((message): message is ConversationMessage => Boolean(message))
  }, [conversation])

  const isRunning = useMemo(() => {
    if (!conversation) {
      return false
    }
    const activeRunId = resolveActiveRunId(conversation)
    if (!activeRunId) {
      return false
    }
    const run = conversation.runsById[activeRunId]
    return run ? ACTIVE_RUN_STATUSES.has(run.status) : false
  }, [conversation])

  const plan = useConversationStore((state) => {
    if (!currentSessionId) {
      return null
    }
    return state.planBySessionId[currentSessionId] ?? null
  })

  const hasMore = conversation?.hasMore ?? false
  const oldestLoadedTurnId = conversation?.nextBeforeTurnId ?? null

  return { messages, isRunning, plan, hasMore, oldestLoadedTurnId }
}
