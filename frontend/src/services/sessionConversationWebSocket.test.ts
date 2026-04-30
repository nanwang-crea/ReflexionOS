import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionConversationWebSocket } from './sessionConversationWebSocket'

const sentMessages: string[] = []
const webSocketInstances: MockWebSocket[] = []

class MockWebSocket {
  static OPEN = 1

  readonly url: string
  readyState = MockWebSocket.OPEN
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((error: unknown) => void) | null = null
  onclose:
    | ((event: { code: number; reason: string; wasClean: boolean }) => void)
    | null = null

  constructor(url: string) {
    this.url = url
    webSocketInstances.push(this)
  }

  send(message: string) {
    sentMessages.push(message)
  }

  close() {
    this.readyState = 3
  }
}

vi.mock('./runtimeConfig', () => ({
  getSessionConversationWebSocketUrl: (sessionId: string) =>
    `ws://localhost/ws/sessions/${sessionId}/conversation`,
}))

beforeEach(() => {
  sentMessages.length = 0
  webSocketInstances.length = 0
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SessionConversationWebSocket', () => {
  it('sends colon-style conversation command types', async () => {
    const ws = new SessionConversationWebSocket()
    const connected = ws.connect('session-1')

    webSocketInstances[0].onopen?.()
    await connected

    ws.sendSync(9)
    ws.startTurn({
      content: 'inspect repo',
      providerId: 'provider-a',
      modelId: 'model-a',
    })
    ws.cancelRun('run-1')

    expect(sentMessages.map((message) => JSON.parse(message).type)).toEqual([
      'conversation:sync',
      'conversation:start_turn',
      'conversation:cancel_run',
    ])
  })

  it('routes colon-style server message types to internal events', async () => {
    const ws = new SessionConversationWebSocket()
    const durableEvents: unknown[] = []
    const plans: unknown[] = []

    ws.on('conversation:event', (event) => durableEvents.push(event))
    ws.on('plan:updated', (plan) => plans.push(plan))

    const connected = ws.connect('session-1')
    webSocketInstances[0].onopen?.()
    await connected

    webSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        type: 'conversation:event',
        data: { id: 'evt-1', event_type: 'message.created' },
      }),
    })
    webSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        type: 'plan:updated',
        data: { goal: 'inspect', steps: [], current_step_index: 0 },
      }),
    })

    expect(durableEvents).toEqual([{ id: 'evt-1', event_type: 'message.created' }])
    expect(plans).toEqual([{ goal: 'inspect', steps: [], current_step_index: 0 }])
  })
})
