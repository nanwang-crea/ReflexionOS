/**
 * 文件功能：transcriptItems 模块（buildTranscriptItems / isProcessGroupStreaming）的测试
 * 文件描述：验证会话消息列表被正确归并为可渲染的转录条目（process_group 过程分组、answer_message 回答消息等），
 * 覆盖工具调用分组、按时间间隔拆分子分组、跨运行/跨助手回答拆分分组、批准等待态、委托关联键保留、思考与工作笔记归类、流式状态检测等场景
 * 核心逻辑：构造一系列 ConversationMessage，调用 buildTranscriptItems 转换为转录条目树（process_group 下可含 tool_group/thinking/working_note 等 subItems），断言分组结构、字段值及流式检测结果是否符合预期
 */
import { describe, expect, it } from 'vitest'
import type { ConversationMessage } from '@/types/conversation'
import { buildTranscriptItems, isProcessGroupStreaming } from '../transcriptItems'

/**
 * 函数名：buildMessage
 * 入参：
 *   - overrides (Partial<ConversationMessage>，可选): 需要覆盖的字段，未传字段使用默认值
 * 功能：构造一条测试用的会话消息对象（ConversationMessage），减少各测试用例重复编写完整消息结构
 * 运行逻辑：返回一份带有默认字段值的消息对象，并用 overrides 中的字段覆盖对应默认值
 * 出参：ConversationMessage - 构造好的会话消息对象
 */
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

/**
 * 函数名：getProcessGroup
 * 入参：
 *   - items (ReturnType<typeof buildTranscriptItems>): buildTranscriptItems 返回的转录条目数组
 *   - index (number): 要取的条目下标
 * 功能：从转录条目数组中按下标取出一个条目，并断言其类型为 process_group（过程分组），否则返回 null
 * 运行逻辑：取出对应下标的条目，检查 kind 字段是否为 'process_group'，不是则返回 null 便于测试用例做类型收窄
 * 出参：process_group 类型的条目对象，或 null（下标对应条目不是 process_group 时）
 */
function getProcessGroup(items: ReturnType<typeof buildTranscriptItems>, index: number) {
  const item = items[index]
  if (item?.kind !== 'process_group') return null
  return item
}

/**
 * 函数名：getToolGroupFromProcess
 * 入参：
 *   - processGroup ({ kind: 'process_group'; subItems: ProcessSubItem[] }): 过程分组对象
 *   - toolGroupIndex (number): 要取的子条目下标
 * 功能：从过程分组的 subItems 中按下标取出一个子条目，并断言其类型为 tool_group（工具调用分组），否则返回 null
 * 运行逻辑：取出对应下标的子条目，检查 kind 字段是否为 'tool_group'，不是则返回 null 便于测试用例做类型收窄
 * 出参：tool_group 类型的子条目对象，或 null（下标对应子条目不是 tool_group 时）
 */
function getToolGroupFromProcess(processGroup: { kind: 'process_group'; subItems: import('../transcriptItems').ProcessSubItem[] }, toolGroupIndex: number) {
  const sub = processGroup.subItems[toolGroupIndex]
  if (sub?.kind !== 'tool_group') return null
  return sub
}

// 测试目标：buildTranscriptItems —— 将扁平的会话消息列表转换为分组后的转录条目树
describe('buildTranscriptItems', () => {
  // 场景：连续的工具调用轨迹应被包裹进 process_group，紧随其后的助手正文回答应被拆分为独立的 answer_message 条目
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

  // 场景：同一个 run 内，若相邻工具调用之间的时间间隔过大，应拆分成多个独立的工具调用子分组（tool_group）
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

  // 场景：当助手正文回答出现在两段工具调用之间时，应将其前后的工具调用拆分成两个独立的 process_group
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

  // 场景：处于等待批准状态（waiting_for_approval）的 shell 工具调用轨迹应保持在"等待中"的收据状态，且摘要文案正确展示待执行命令
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

  // 场景：delegate（委托子代理）类型的工具调用轨迹，其关联键（tool_call_id、session_id 等）应被完整保留到转换后的详情对象中
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

  // 场景（参数化）：approved（已批准）/denied（已拒绝）两种审批决定分别应映射为对应的终态分组状态（completed/cancelled）
  // 和详情状态（success/cancelled），且不再残留等待中的 approval 信息
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

  // 场景：带有 reasoning_text（推理文本）的助手消息，其推理内容应被放入 process_group 的 subItems 中作为 thinking 条目，正文内容则作为独立的 answer_message
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

  // 场景：displayMode 为 working_note（工作笔记）的助手消息，应作为 working_note 类型的子条目被放入 process_group 的 subItems 中
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

  // 场景：验证 isProcessGroupStreaming 函数能正确根据 subItems 中各条目的 streamState 判断整个过程分组是否仍处于流式生成中
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
