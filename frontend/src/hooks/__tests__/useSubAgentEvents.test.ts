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
