// 文件功能：useSubAgentEventsStore 的单元测试
// 文件描述：验证子 agent 事件按 sessionId + delegate_call_id 双键隔离存储，不同会话的同名
// delegate_call_id 不会互相污染；以及 clearSession 只清指定会话的记录，不影响其他会话
// 核心逻辑：直接操作真实的 zustand store（每个用例前 clearAll 重置），调用 addEvent/clearSession
// 后断言 stepsBySessionId 的内容
import { beforeEach, describe, expect, it } from 'vitest'
import { useSubAgentEventsStore } from '../useSubAgentEvents'

describe('useSubAgentEventsStore', () => {
  beforeEach(() => {
    useSubAgentEventsStore.getState().clearAll()
  })

  it('stores sub-agent events per session and delegate call id', () => {
    const store = useSubAgentEventsStore.getState()

    store.addEvent('session-1', {
      event_type: 'tool:start',
      delegate_call_id: 'call-1',
      payload: { tool_name: 'file' },
    })
    store.addEvent('session-2', {
      event_type: 'tool:start',
      delegate_call_id: 'call-1',
      payload: { tool_name: 'shell' },
    })

    const state = useSubAgentEventsStore.getState()
    expect(state.stepsBySessionId.get('session-1')?.get('call-1')?.[0].payload.tool_name).toBe('file')
    expect(state.stepsBySessionId.get('session-2')?.get('call-1')?.[0].payload.tool_name).toBe('shell')
  })

  it('clears one session without deleting another session history', () => {
    const store = useSubAgentEventsStore.getState()

    store.addEvent('session-1', {
      event_type: 'tool:start',
      delegate_call_id: 'call-1',
      payload: { tool_name: 'file' },
    })
    store.addEvent('session-2', {
      event_type: 'tool:start',
      delegate_call_id: 'call-1',
      payload: { tool_name: 'shell' },
    })

    store.clearSession('session-1')

    const state = useSubAgentEventsStore.getState()
    expect(state.stepsBySessionId.has('session-1')).toBe(false)
    expect(state.stepsBySessionId.get('session-2')?.get('call-1')).toHaveLength(1)
  })
})
