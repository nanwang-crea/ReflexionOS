import { useEffect } from 'react'
import { useConversationStore } from '@/features/conversation/stores/conversation.store'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'

// 维护“当前会话已读基线”的单一收敛点：
// 只要某会话是当前查看的会话，就把它的已读序号追到最新事件序号。
// 这样用户正在看的会话永远不会累积未读；离开后该会话再增长的事件才算未读。
//
// 把更新逻辑收敛到这一个 effect，避免未读标记在多处更新时抖动
// （需求规范要求“何时算成功查看会话”必须只有一个判定点）。
// 函数名：useSessionUnreadState
// 入参：
//   - currentSessionId (string | null): 当前正在查看的会话 ID，为 null 表示未查看任何会话
// 功能：将“当前查看会话”的已读序号持续追平到最新事件序号，避免其未读数累积
// 运行逻辑：
//   1. 订阅当前会话最新的 lastEventSeq（每次快照写入/新事件到达都会变化）
//   2. 依赖 currentSessionId、currentLastEventSeq、markSessionSeen 建立 effect
//   3. effect 内若会话为空或序号未知则跳过，否则调用 markSessionSeen 更新已读基线
// 出参：无（副作用 hook，仅更新 workspace.store 中的已读状态）
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
