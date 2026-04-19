import { describe, expect, it, vi } from 'vitest'
import { ExecutionWebSocket } from './websocketClient'

describe('ExecutionWebSocket.startExecution', () => {
  it('sends project_id so the backend can resolve the execution path itself', () => {
    const send = vi.fn()
    const websocket = new ExecutionWebSocket()

    ;(websocket as unknown as { ws: { readyState: number; send: typeof send } }).ws = {
      readyState: WebSocket.OPEN,
      send,
    }

    websocket.startExecution('Run task', 'proj-reflexion', 'provider-a', 'model-a')

    expect(send).toHaveBeenCalledWith(JSON.stringify({
      type: 'start',
      data: {
        task: 'Run task',
        project_id: 'proj-reflexion',
        provider_id: 'provider-a',
        model_id: 'model-a',
      },
    }))
  })
})
