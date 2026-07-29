/**
 * useSubAgentEvents — 子 agent 执行事件的全局 zustand store。
 *
 * 由 useConversationRuntime 的 WebSocket sub_agent:event 处理器写入，
 * 由 DelegateToolCall 组件直接读取，实现子 agent 执行步骤的实时展示。
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
  /** 按 delegate_call_id 分组的步骤映射 */
  steps: Map<string, SubAgentStep[]>

  /** 添加一条子 agent 事件 */
  addEvent: (event: SubAgentEventDto) => void

  /** 清除指定 delegate_call_id 的步骤 */
  clearSteps: (callId: string) => void

  /** 清除所有步骤 */
  clearAll: () => void
}

export const useSubAgentEventsStore = create<SubAgentEventsState>((set) => ({
  steps: new Map(),

  addEvent: (event) => {
    const callId = event.delegate_call_id
    if (!callId) return

    set((state) => {
      const existing = state.steps.get(callId) ?? []
      const step: SubAgentStep = {
        eventType: event.event_type,
        payload: event.payload,
        receivedAt: Date.now(),
      }
      const newMap = new Map(state.steps)
      newMap.set(callId, [...existing, step])
      return { steps: newMap }
    })
  },

  clearSteps: (callId) => {
    set((state) => {
      const newMap = new Map(state.steps)
      newMap.delete(callId)
      return { steps: newMap }
    })
  },

  clearAll: () => {
    set({ steps: new Map() })
  },
}))

const EMPTY_SUB_AGENT_STEPS: SubAgentStep[] = []

/**
 * 获取指定 delegate_call_id 的子 agent 步骤。
 * 供组件在 render 中调用，自动订阅 store 变化。
 */
export function useSubAgentSteps(callId: string | undefined): SubAgentStep[] {
  return useSubAgentEventsStore((state) =>
    callId ? (state.steps.get(callId) ?? EMPTY_SUB_AGENT_STEPS) : EMPTY_SUB_AGENT_STEPS
  )
}
