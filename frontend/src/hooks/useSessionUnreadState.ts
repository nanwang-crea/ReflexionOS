import { useEffect } from 'react'
import { useConversationStore } from '@/features/conversation/stores/conversation.store'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'

// 维护“当前会话已读基线”的单一收敛点：
// 只要某会话是当前查看的会话，就把它的已读序号追到最新事件序号。
// 这样用户正在看的会话永远不会累积未读；离开后该会话再增长的事件才算未读。
//
// 把更新逻辑收敛到这一个 effect，避免未读标记在多处更新时抖动
// （需求规范要求“何时算成功查看会话”必须只有一个判定点）。
export function useSessionUnreadState(currentSessionId: string | null) {
  // 订阅当前会话的最新事件序号；它在快照写入和每个事件后都会更新。
  const currentLastEventSeq = useConversationStore((state) => {
    if (!currentSessionId) {
      return undefined
    }
    return state.conversationsBySessionId[currentSessionId]?.lastEventSeq
  })

  const markSessionSeen = useWorkspaceStore((state) => state.markSessionSeen)

  useEffect(() => {
    if (!currentSessionId || currentLastEventSeq === undefined) {
      return
    }
    markSessionSeen(currentSessionId, currentLastEventSeq)
  }, [currentSessionId, currentLastEventSeq, markSessionSeen])
}
