import { describe, expect, it } from 'vitest'
import type { ConversationMessage } from '@/types/conversation'
import { buildTranscriptItems, isProcessGroupStreaming } from '../transcriptItems'

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

function getProcessGroup(items: ReturnType<typeof buildTranscriptItems>, index: number) {
  const item = items[index]
  if (item?.kind !== 'process_group') return null
  return item
}

function getToolGroupFromProcess(processGroup: { kind: 'process_group'; subItems: import('../transcriptItems').ProcessSubItem[] }, toolGroupIndex: number) {
  const sub = processGroup.subItems[toolGroupIndex]
  if (sub?.kind !== 'tool_group') return null
  return sub
}

describe('buildTranscriptItems', () => {
  it('wraps tool traces in process_group, separates assistant answers as answer_message', () => {
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
        runId: 'run-2',
        createdAt: '2026-04-24T10:00:25Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'search', query: 'conversation:event' },
        },
      }),
    ])

    expect(items.map((item) => item.kind)).toEqual(['process_group', 'answer_message', 'process_group'])

    const pg0 = getProcessGroup(items, 0)!
    expect(pg0.runId).toBe('run-1')
    const tg0 = getToolGroupFromProcess(pg0, 0)!
    expect(tg0.id).toBe('tools-msg-tool-read')
    expect(tg0.status).toBe('completed')
    expect(tg0.details).toHaveLength(2)

    expect(items[1].kind).toBe('answer_message')
    if (items[1].kind === 'answer_message') {
      expect(items[1].message.id).toBe('msg-assistant')
    }

    const pg2 = getProcessGroup(items, 2)!
    expect(pg2.runId).toBe('run-2')
    const tg2 = getToolGroupFromProcess(pg2, 0)!
    expect(tg2.details).toHaveLength(1)
  })

  it('splits tool trace sub-groups when the time gap is large within same run', () => {
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

    expect(items.map((item) => item.kind)).toEqual(['process_group'])
    const pg = getProcessGroup(items, 0)!
    expect(pg.subItems.filter((s) => s.kind === 'tool_group')).toHaveLength(2)
    const toolGroups = pg.subItems.filter((s) => s.kind === 'tool_group')
    if (toolGroups[0].kind === 'tool_group') {
      expect(toolGroups[0].details[0].target).toBe('src/app.ts')
    }
    if (toolGroups[1].kind === 'tool_group') {
      expect(toolGroups[1].details[0].target).toBe('src/main.ts')
    }
  })

  it('separates process groups when assistant answer appears between tool runs', () => {
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
        runId: 'run-2',
        createdAt: '2026-04-24T10:00:20Z',
        payloadJson: {
          tool_name: 'file',
          arguments: { action: 'search', query: 'plan:updated' },
        },
      }),
    ])

    expect(items.map((item) => item.kind)).toEqual(['process_group', 'answer_message', 'process_group'])

    const pg0 = getProcessGroup(items, 0)!
    const tg0 = getToolGroupFromProcess(pg0, 0)!
    expect(tg0.messages.map((m: ConversationMessage) => m.id)).toEqual(['msg-tool-before'])

    const pg2 = getProcessGroup(items, 2)!
    const tg2 = getToolGroupFromProcess(pg2, 0)!
    expect(tg2.messages.map((m: ConversationMessage) => m.id)).toEqual(['msg-tool-after'])
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

    const pg = getProcessGroup(items, 0)!
    const tg = getToolGroupFromProcess(pg, 0)!
    expect(tg.status).toBe('waiting_for_approval')
    expect(tg.details[0]).toMatchObject({
      status: 'waiting_for_approval',
      summary: '运行 git push origin feature/approveRunTime',
    })
  })

  it('preserves delegate correlation keys on tool trace details', () => {
    const items = buildTranscriptItems([
      buildMessage({
        id: 'msg-delegate',
        sessionId: 'session-chat',
        payloadJson: {
          tool_name: 'delegate',
          tool_call_id: 'delegate-call-123',
          arguments: { task: '检查后端审批路径' },
        },
      }),
    ])

    const pg = getProcessGroup(items, 0)!
    const tg = getToolGroupFromProcess(pg, 0)!
    expect(tg.details[0]).toMatchObject({
      id: 'msg-delegate',
      toolName: 'delegate',
      data: {
        tool_call_id: 'delegate-call-123',
        session_id: 'session-chat',
      },
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

      const pg = getProcessGroup(items, 0)!
      const tg = getToolGroupFromProcess(pg, 0)!
      expect(tg.status).toBe(expectedGroupStatus)
      expect(tg.details[0].status).toBe(expectedDetailStatus)
      expect(tg.details[0].approval).toBeUndefined()
    }
  )

  it('places thinking into process_group subItems', () => {
    const items = buildTranscriptItems([
      buildMessage({
        id: 'msg-thinking',
        messageType: 'assistant_message',
        streamState: 'completed',
        contentText: '最终回答',
        payloadJson: { reasoning_text: '我在思考这个问题...' },
        createdAt: '2026-04-24T10:00:00Z',
      }),
    ])

    expect(items.map((item) => item.kind)).toEqual(['process_group', 'answer_message'])
    const pg = getProcessGroup(items, 0)!
    expect(pg.subItems[0].kind).toBe('thinking')
    if (pg.subItems[0].kind === 'thinking') {
      expect(pg.subItems[0].text).toBe('我在思考这个问题...')
    }
    if (items[1].kind === 'answer_message') {
      expect(items[1].message.contentText).toBe('最终回答')
    }
  })

  it('places working_note into process_group subItems', () => {
    const items = buildTranscriptItems([
      buildMessage({
        id: 'msg-wn',
        messageType: 'assistant_message',
        displayMode: 'working_note',
        contentText: '正在搜索文件...',
        payloadJson: {},
        createdAt: '2026-04-24T10:00:00Z',
      }),
    ])

    expect(items.map((item) => item.kind)).toEqual(['process_group'])
    const pg = getProcessGroup(items, 0)!
    expect(pg.subItems[0].kind).toBe('working_note')
    if (pg.subItems[0].kind === 'working_note') {
      expect(pg.subItems[0].text).toBe('正在搜索文件...')
    }
  })

  it('detects streaming state in isProcessGroupStreaming', () => {
    const streamingSubItems = [
      { kind: 'thinking' as const, id: 't1', text: '思考', streamState: 'streaming' as const },
    ]
    const completedSubItems = [
      { kind: 'thinking' as const, id: 't1', text: '思考', streamState: 'completed' as const },
    ]
    expect(isProcessGroupStreaming(streamingSubItems)).toBe(true)
    expect(isProcessGroupStreaming(completedSubItems)).toBe(false)
  })
})
