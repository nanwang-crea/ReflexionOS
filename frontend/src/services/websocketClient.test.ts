import { describe, expect, it, vi } from 'vitest'
import { ExecutionWebSocket } from './websocketClient'

describe('ExecutionWebSocket.startExecution', () => {
  it('sends project_path instead of overloading project_id semantics', () => {
    const send = vi.fn()
    const websocket = new ExecutionWebSocket()

    ;(websocket as unknown as { ws: { readyState: number; send: typeof send } }).ws = {
      readyState: WebSocket.OPEN,
      send,
    }

    websocket.startExecution('Run task', '/tmp/reflexion', 'provider-a', 'model-a')

    expect(send).toHaveBeenCalledWith(JSON.stringify({
      type: 'start',
      data: {
        task: 'Run task',
        project_path: '/tmp/reflexion',
        provider_id: 'provider-a',
        model_id: 'model-a',
      },
    }))
  })
})
