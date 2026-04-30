import { describe, expect, it } from 'vitest'
import type { ConversationMessage } from '@/types/conversation'
import { buildTranscriptItems } from './transcriptItems'

function buildMessage(overrides: Partial<ConversationMessage> = {}): ConversationMessage {
  return {
    id: 'msg-1',
    sessionId: 'session-1',
    turnId: 'turn-1',
    runId: 'run-1',
    turnMessageIndex: 1,
    role: 'assistant',
    messageType: 'tool_trace',
    streamState: 'completed',
    displayMode: 'default',
    contentText: '',
    payloadJson: {},
    createdAt: '2026-04-24T10:00:00Z',
    updatedAt: '2026-04-24T10:00:00Z',
    completedAt: '2026-04-24T10:00:01Z',
    ...overrides,
  }
}

describe('buildTranscriptItems', () => {
  it('groups contiguous tool traces while preserving assistant messages in the timeline', () => {
    const items = buildTranscriptItems([
      buildMessage({
        id: 'msg-tool-read',
        turnMessageIndex: 1,
        createdAt: '2026-04-24T10:00:00Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'read', path: '/tmp/reflexion/src/app.ts' },
        },
      }),
      buildMessage({
        id: 'msg-tool-command',
        turnMessageIndex: 2,
        createdAt: '2026-04-24T10:00:15Z',
        payloadJson: {
          tool_name: 'shell',
          arguments: { command: 'pnpm test' },
        },
      }),
      buildMessage({
        id: 'msg-assistant',
        turnMessageIndex: 3,
        role: 'assistant',
        messageType: 'assistant_message',
        contentText: '我找到问题了。',
        createdAt: '2026-04-24T10:00:20Z',
      }),
      buildMessage({
        id: 'msg-tool-search',
        turnMessageIndex: 4,
        createdAt: '2026-04-24T10:00:25Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'search', query: 'conversation:event' },
        },
      }),
    ])

    expect(items.map((item) => item.kind)).toEqual(['tool_group', 'message', 'tool_group'])
    expect(items[0]).toMatchObject({
      kind: 'tool_group',
      id: 'tools-msg-tool-read-msg-tool-command',
      status: 'completed',
    })
    expect(items[0].kind === 'tool_group' ? items[0].details : []).toHaveLength(2)
    expect(items[1].kind === 'message' ? items[1].message.id : null).toBe('msg-assistant')
    expect(items[2].kind === 'tool_group' ? items[2].details : []).toHaveLength(1)
  })

  it('splits tool trace groups when the time gap is large', () => {
    const items = buildTranscriptItems([
      buildMessage({
        id: 'msg-tool-1',
        createdAt: '2026-04-24T10:00:00Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'read', path: '/tmp/reflexion/src/app.ts' },
        },
      }),
      buildMessage({
        id: 'msg-tool-2',
        turnMessageIndex: 2,
        createdAt: '2026-04-24T10:04:00Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'read', path: '/tmp/reflexion/src/main.ts' },
        },
      }),
    ])

    expect(items.map((item) => item.kind)).toEqual(['tool_group', 'tool_group'])
    expect(items[0].kind === 'tool_group' ? items[0].details[0].target : null).toBe('src/app.ts')
    expect(items[1].kind === 'tool_group' ? items[1].details[0].target : null).toBe('src/main.ts')
  })

  it('never merges tool traces across assistant replies', () => {
    const items = buildTranscriptItems([
      buildMessage({
        id: 'msg-tool-before',
        turnMessageIndex: 1,
        createdAt: '2026-04-24T10:00:00Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'read', path: '/tmp/reflexion/src/app.ts' },
        },
      }),
      buildMessage({
        id: 'msg-assistant',
        turnMessageIndex: 2,
        role: 'assistant',
        messageType: 'assistant_message',
        contentText: '这里先说明一下发现。',
        createdAt: '2026-04-24T10:00:10Z',
      }),
      buildMessage({
        id: 'msg-tool-after',
        turnMessageIndex: 3,
        createdAt: '2026-04-24T10:00:20Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'search', query: 'plan:updated' },
        },
      }),
    ])

    expect(items.map((item) => item.kind)).toEqual(['tool_group', 'message', 'tool_group'])
    expect(items[0].kind === 'tool_group' ? items[0].messages.map((message) => message.id) : []).toEqual([
      'msg-tool-before',
    ])
    expect(items[2].kind === 'tool_group' ? items[2].messages.map((message) => message.id) : []).toEqual([
      'msg-tool-after',
    ])
  })

  it('keeps approval-required shell traces in a waiting receipt state', () => {
    const items = buildTranscriptItems([
      buildMessage({
        id: 'msg-approval',
        streamState: 'idle',
        payloadJson: {
          tool_name: 'shell',
          status: 'waiting_for_approval',
          arguments: { command: 'git push origin feature/approveRunTime' },
        },
      }),
    ])

    expect(items[0]).toMatchObject({
      kind: 'tool_group',
      status: 'waiting_for_approval',
    })
    expect(items[0].kind === 'tool_group' ? items[0].details[0] : null).toMatchObject({
      status: 'waiting_for_approval',
      summary: '运行 git push origin feature/approveRunTime',
    })
  })

  it.each([
    ['approved', 'completed', 'success'],
    ['denied', 'cancelled', 'cancelled'],
  ] as const)(
    'maps %s approval decisions to terminal non-waiting receipts',
    (status, expectedGroupStatus, expectedDetailStatus) => {
      const items = buildTranscriptItems([
        buildMessage({
          id: `msg-${status}`,
          streamState: 'idle',
          payloadJson: {
            tool_name: 'shell',
            status,
            approval_id: 'approval-1',
            arguments: { command: 'git push origin feature/approveRunTime' },
          },
        }),
      ])

      expect(items[0]).toMatchObject({
        kind: 'tool_group',
        status: expectedGroupStatus,
      })
      const detail = items[0].kind === 'tool_group' ? items[0].details[0] : null
      expect(detail?.status).toBe(expectedDetailStatus)
      expect(detail?.approval).toBeUndefined()
    }
  )
})
