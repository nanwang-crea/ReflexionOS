/**
 * useSubAgentEvents — 子 agent 执行事件的全局 zustand store。
 *
 * 由 useConversationRuntime 的 WebSocket sub_agent:event 处理器写入，
 * 由 DelegateToolCall 组件直接读取，实现子 agent 执行步骤的实时展示。
 * 事件按 sessionId + delegate_call_id 双键存储，避免多会话并行运行时
 * 相同 tool_call_id 的子任务互相污染。
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

  /** 添加一条子 agent 事件 */
  addEvent: (sessionId: string, event: SubAgentEventDto) => void

  /** 清除指定 sessionId + delegate_call_id 的步骤 */
  clearSteps: (sessionId: string, callId: string) => void

  /** 清除指定 sessionId 的所有步骤 */
  clearSession: (sessionId: string) => void

  /** 清除所有步骤 */
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
 * 获取指定 sessionId + delegate_call_id 的子 agent 步骤。
 * 供组件在 render 中调用，自动订阅 store 变化。
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
