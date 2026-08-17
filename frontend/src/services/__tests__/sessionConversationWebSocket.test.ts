// SessionConversationWebSocket 的单测：验证客户端发出的“冒号风格”指令消息格式，以及收到服务端消息后能否正确路由为内部事件（会话事件、计划更新、子agent事件）。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionConversationWebSocket } from '../sessionConversationWebSocket'

const sentMessages: string[] = []
const webSocketInstances: MockWebSocket[] = []

// 用于替换全局 WebSocket 的测试替身：不发起真实网络连接，仅记录发送内容并允许测试手动触发 onopen/onmessage 回调。
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
  // 参数：无。
  // 验证：sendSync/startTurn/cancelRun/approveTool/denyTool 等方法发出的消息 type 均为“冒号风格”命名，且审批/拒绝消息的 data 字段按下划线命名转换正确。
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
    ws.approveTool({ runId: 'run-1', approvalId: 'approval-1' })
    ws.denyTool({ runId: 'run-1', approvalId: 'approval-1' })

    expect(sentMessages.map((message) => JSON.parse(message).type)).toEqual([
      'conversation:sync',
      'conversation:start_turn',
      'conversation:cancel_run',
      'conversation:approve_tool',
      'conversation:deny_tool',
    ])
    expect(JSON.parse(sentMessages[3]).data).toEqual({
      approval_id: 'approval-1',
      run_id: 'run-1',
    })
    expect(JSON.parse(sentMessages[4]).data).toEqual({
      approval_id: 'approval-1',
      run_id: 'run-1',
    })
  })

  // 参数：无。
  // 验证：服务端推送的 conversation:event / plan:updated 冒号风格消息类型，能被正确路由到对应的内部事件监听器（durableEvents、plans）。
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
        data: { goal: 'inspect', steps: [] },
      }),
    })

    expect(durableEvents).toEqual([{ id: 'evt-1', event_type: 'message.created' }])
    expect(plans).toEqual([{ goal: 'inspect', steps: [] }])
  })

  // 参数：无。
  // 验证：子agent相关的服务端消息（sub_agent:tool:start / sub_agent:tool:result）会被归一化为统一的 sub_agent:event 事件，
  // 且 delegate_call_id 经过运行时类型检查——非字符串（如数字 123）会被转为 undefined，而不是直接透传错误类型。
  it('maps sub-agent server messages to runtime-checked sub_agent:event payloads', async () => {
    const ws = new SessionConversationWebSocket()
    const subAgentEvents: unknown[] = []

    ws.on('sub_agent:event', (event) => subAgentEvents.push(event))

    const connected = ws.connect('session-1')
    webSocketInstances[0].onopen?.()
    await connected

    webSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        type: 'sub_agent:tool:start',
        data: {
          delegate_call_id: 'delegate-call-1',
          tool_name: 'shell',
        },
      }),
    })
    webSocketInstances[0].onmessage?.({
      data: JSON.stringify({
        type: 'sub_agent:tool:result',
        data: {
          delegate_call_id: 123,
          tool_name: 'shell',
        },
      }),
    })

    expect(subAgentEvents).toEqual([
      {
        event_type: 'tool:start',
        delegate_call_id: 'delegate-call-1',
        payload: { tool_name: 'shell' },
      },
      {
        event_type: 'tool:result',
        delegate_call_id: undefined,
        payload: { tool_name: 'shell' },
      },
    ])
  })
})
