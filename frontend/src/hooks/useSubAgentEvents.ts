/**
 * 文件功能：子 agent 执行事件的全局 zustand store
 * 文件描述：由 useConversationRuntime 的 WebSocket sub_agent:event 处理器写入，
 * 由 DelegateToolCall 组件直接读取，实现子 agent 执行步骤的实时展示。
 * 事件按 sessionId + delegate_call_id 双键存储，避免多会话并行运行时
 * 相同 tool_call_id 的子任务互相污染。
 * 核心逻辑：所有写操作（addEvent/clearSteps/clearSession/clearAll）都通过不可变更新
 * （复制外层 Map 后再修改）驱动 zustand 的浅比较触发订阅组件重渲染；
 * useSubAgentSteps 是唯一的读取入口，供组件订阅指定会话+调用的步骤列表
 */
import { create } from 'zustand'
import type { SubAgentEventDto } from '@/services/sessionConversationWebSocket'

/** 单条子 agent 执行步骤 */
export interface SubAgentStep {
  /** 事件类型：tool:start | tool:result | tool:error | llm:content */
  eventType: string
  /** 原始事件数据 */
  payload: Record<string, unknown>
  /** 接收时间戳 */
  receivedAt: number
}

interface SubAgentEventsState {
  /** 按 sessionId → delegate_call_id 分组的步骤映射 */
  stepsBySessionId: Map<string, Map<string, SubAgentStep[]>>

  /**
   * 函数名：addEvent
   * 入参：
   *   - sessionId (string): 事件所属的会话 ID
   *   - event (SubAgentEventDto): 后端推送的子 agent 事件，含 delegate_call_id/event_type/payload
   * 功能：把一条子 agent 事件追加到对应 sessionId + delegate_call_id 的步骤列表末尾
   * 运行逻辑：sessionId 或 event.delegate_call_id 为空时直接忽略；否则以不可变方式逐层复制
   * stepsBySessionId -> 该会话的 Map -> 该调用的步骤数组，在数组末尾追加新步骤后写回 state
   * 出参：无（更新 store 状态）
   */
  addEvent: (sessionId: string, event: SubAgentEventDto) => void

  /**
   * 函数名：clearSteps
   * 入参：
   *   - sessionId (string): 目标会话 ID
   *   - callId (string): 目标 delegate_call_id
   * 功能：清除指定会话下某一次子 agent 调用的全部步骤
   * 运行逻辑：若该会话下不存在该 callId 则直接返回原 state（不触发更新）；否则复制该会话的
   * Map 并删除对应 callId，若该会话已无任何调用记录则连同会话一并从外层 Map 删除
   * 出参：无（更新 store 状态）
   */
  clearSteps: (sessionId: string, callId: string) => void

  /**
   * 函数名：clearSession
   * 入参：
   *   - sessionId (string): 目标会话 ID
   * 功能：清除指定会话的所有子 agent 步骤记录（如会话被重置时调用）
   * 运行逻辑：若该会话本就不存在则直接返回原 state；否则复制外层 Map 并删除该会话对应的条目
   * 出参：无（更新 store 状态）
   */
  clearSession: (sessionId: string) => void

  /**
   * 函数名：clearAll
   * 入参：无
   * 功能：清空全部会话的子 agent 步骤记录
   * 运行逻辑：直接将 stepsBySessionId 重置为一个新的空 Map
   * 出参：无（更新 store 状态）
   */
  clearAll: () => void
}

const EMPTY_STEPS: SubAgentStep[] = []

export const useSubAgentEventsStore = create<SubAgentEventsState>((set) => ({
  stepsBySessionId: new Map(),

  addEvent: (sessionId, event) => {
    const callId = event.delegate_call_id
    if (!sessionId || !callId) return

    set((state) => {
      const currentSessionSteps = state.stepsBySessionId.get(sessionId) ?? new Map()
      const nextSessionSteps = new Map(currentSessionSteps)
      const existing = nextSessionSteps.get(callId) ?? []
      const step: SubAgentStep = {
        eventType: event.event_type,
        payload: event.payload,
        receivedAt: Date.now(),
      }
      nextSessionSteps.set(callId, [...existing, step])

      const next = new Map(state.stepsBySessionId)
      next.set(sessionId, nextSessionSteps)
      return { stepsBySessionId: next }
    })
  },

  clearSteps: (sessionId, callId) => {
    set((state) => {
      const currentSessionSteps = state.stepsBySessionId.get(sessionId)
      if (!currentSessionSteps?.has(callId)) {
        return state
      }

      const nextSessionSteps = new Map(currentSessionSteps)
      nextSessionSteps.delete(callId)

      const next = new Map(state.stepsBySessionId)
      if (nextSessionSteps.size === 0) {
        next.delete(sessionId)
      } else {
        next.set(sessionId, nextSessionSteps)
      }
      return { stepsBySessionId: next }
    })
  },

  clearSession: (sessionId) => {
    set((state) => {
      if (!state.stepsBySessionId.has(sessionId)) {
        return state
      }
      const next = new Map(state.stepsBySessionId)
      next.delete(sessionId)
      return { stepsBySessionId: next }
    })
  },

  clearAll: () => {
    set({ stepsBySessionId: new Map() })
  },
}))

/**
 * 函数名：useSubAgentSteps
 * 入参：
 *   - sessionId (string | undefined): 目标会话 ID，未选中会话时为 undefined
 *   - callId (string | undefined): 目标 delegate_call_id（子 agent 调用 ID），未知时为 undefined
 * 功能：获取指定 sessionId + delegate_call_id 的子 agent 执行步骤列表，供组件在 render 中调用，
 * 自动订阅 store 变化
 * 运行逻辑：sessionId 或 callId 任一缺失时返回固定的空数组 EMPTY_STEPS（避免每次渲染创建新数组
 * 导致下游不必要的重渲染）；否则从 stepsBySessionId 中按双键查找对应步骤数组，查不到也回退到
 * EMPTY_STEPS
 * 出参：SubAgentStep[] - 该次子 agent 调用当前已收到的步骤列表（按接收顺序排列）
 */
export function useSubAgentSteps(
  sessionId: string | undefined,
  callId: string | undefined,
): SubAgentStep[] {
  return useSubAgentEventsStore((state) => (
    sessionId && callId
      ? state.stepsBySessionId.get(sessionId)?.get(callId) ?? EMPTY_STEPS
      : EMPTY_STEPS
  ))
}
