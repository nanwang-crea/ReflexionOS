/**
 * 文件功能：ToolTraceCard / ToolTraceGroup 及 WorkspaceTranscript 组件测试
 * 文件描述：覆盖工具调用轨迹卡片（收起态摘要、批准/拒绝控制、批准动作发送）以及会话转录组件（消息分组渲染、滚动跟随、虚拟列表索引、思考块展开等）的行为
 * 核心逻辑：使用 renderToStaticMarkup 做纯服务端渲染的快照式断言（检查生成的 HTML 是否包含/不包含特定文本或样式类）；对 framer-motion、react-virtuoso、MarkdownRenderer 等重依赖模块做轻量 mock，避免测试环境需要真实动画/虚拟列表/浏览器 API
 */
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { sendApprovalAction } from '@/components/execution/approvalActions'
import type { ConversationMessage } from '@/types/conversation'
import { ToolTraceCard, ToolTraceGroup } from '../ToolTraceCard'
import { WorkspaceTranscript } from '../WorkspaceTranscript'
import { buildToolTraceDetail, type TranscriptItem } from '../transcriptItems'

// 模拟 localStorage：测试环境下部分组件可能读取本地存储（如折叠状态），这里提供空实现避免报错
const localStorageMock = {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
}

vi.stubGlobal('localStorage', localStorageMock)

interface MockVirtuosoProps {
  data?: TranscriptItem[]
  itemContent: (index: number, item: TranscriptItem) => React.ReactNode
  components?: {
    Header?: () => React.ReactNode
    Footer?: () => React.ReactNode
    Scroller?: React.ComponentType<{
      children?: React.ReactNode
      style?: React.CSSProperties
      'data-virtuoso-scroller'?: boolean
    }>
  }
  atBottomStateChange?: (isAtBottom: boolean) => void
  startReached?: () => void
  firstItemIndex?: number
  atBottomThreshold?: number
  followOutput?: boolean | 'smooth' | ((isAtBottom: boolean) => boolean | 'smooth')
  computeItemKey?: (index: number, item: TranscriptItem) => React.Key
  alignToBottom?: boolean
  initialTopMostItemIndex?: number
}

// 记录最近一次传给 mock 版 Virtuoso 组件的 props，供测试用例断言虚拟列表相关行为（如 firstItemIndex、computeItemKey）
let latestVirtuosoProps: MockVirtuosoProps | null = null
// 控制 mock 版 Virtuoso 是否在渲染时立即触发 startReached 回调，用于模拟"是否已发生过向上滚动交互"的场景
let shouldInvokeStartReached = true

// 模拟 framer-motion：测试环境不需要真实动画，AnimatePresence 直接透传 children，motion.div/span/button 退化为普通 DOM 元素
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement> & { children?: React.ReactNode }) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: React.HTMLAttributes<HTMLSpanElement> & { children?: React.ReactNode }) => <span {...props}>{children}</span>,
    button: ({ children, ...props }: React.HTMLAttributes<HTMLButtonElement> & { children?: React.ReactNode }) => <button {...props}>{children}</button>,
  },
}))

// 模拟 react-virtuoso 的 Virtuoso 组件：真实虚拟列表依赖浏览器测量能力，测试环境改为直接同步渲染全部 data 项
// 同时按需触发 atBottomStateChange / startReached 回调，模拟"是否处于底部"和"触发向上加载更多"等交互
vi.mock('react-virtuoso', () => {
  return {
    Virtuoso: (props: MockVirtuosoProps) => {
      latestVirtuosoProps = props
      const { data, itemContent, components, atBottomStateChange, startReached } = props
      const isAtBottom = Boolean(data && data.length > 0)
      if (atBottomStateChange) atBottomStateChange(isAtBottom)
      if (startReached && shouldInvokeStartReached) startReached()
      const header = components?.Header?.()
      const footer = components?.Footer?.()
      const content = React.createElement(React.Fragment, null,
        header,
        (data || []).map((item, index) => React.createElement(React.Fragment, { key: item.id }, itemContent(index, item))),
        footer
      )
      if (components?.Scroller) {
        return React.createElement(
          components.Scroller,
          { 'data-virtuoso-scroller': true, style: { height: 400 } },
          content
        )
      }
      return React.createElement('div', null, content)
    },
  }
})

// 模拟 MarkdownRenderer：测试只需验证内容和流式状态是否传递正确，不需要真实的 Markdown 解析渲染
vi.mock('@/components/chat/MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content, className, isStreaming }: { content: string; className?: string; isStreaming?: boolean }) => (
    <div className={className} data-markdown-streaming={String(Boolean(isStreaming))}>{content}</div>
  ),
}))

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

// 测试目标：ToolTraceCard（单条工具调用轨迹卡片）与 ToolTraceGroup（工具调用分组，含批准/拒绝控制）
describe('ToolTraceCard', () => {
  // 场景：默认情况下，工具调用轨迹应折叠展示为一条简洁的"操作收据"摘要，不暴露具体参数和输出内容
  it('renders a collapsed action receipt summary for tool traces by default', () => {
    const html = renderToStaticMarkup(
      <ToolTraceCard
        message={buildMessage({
          payloadJson: {
            tool_name: 'file',
            status: 'completed',
            arguments: { action: 'read', path: '/tmp/reflexion/src/app.py' },
            output: 'hello',
            duration: 120,
          },
        })}
      />
    )

    expect(html).toContain('已探索 1 个文件')
    expect(html).toContain('mb-8 max-w-[920px] mx-auto w-full')
    expect(html).not.toContain('探索 src/app.py')
    expect(html).not.toContain('action')
    expect(html).not.toContain('hello')
  })

  // 场景：等待批准的工具调用轨迹应展示为"活跃状态"的收据，且摘要文案保持稳定（如显示即将执行的命令）
  it('renders approval-required traces as active receipts with stable summaries', () => {
    const html = renderToStaticMarkup(
      <ToolTraceCard
        message={buildMessage({
          streamState: 'idle',
          payloadJson: {
            tool_name: 'shell',
            status: 'waiting_for_approval',
            arguments: { command: 'git push origin feature/approveRunTime' },
          },
        })}
      />
    )

    expect(html).toContain('运行 git push origin feature/approveRunTime')
    expect(html).not.toContain('已运行')
  })

  // 场景：当轨迹具备明确的批准元数据（runId + approvalId）时，等待批准的分组应显示紧凑的"批准/拒绝"操作控件，
  // 并且传给批准回调的 approval 对象只应包含 runId/approvalId，不应携带命令或参数等多余信息
  it('adds compact approval controls for waiting traces with concrete approval metadata', () => {
    const approvalAction = vi.fn()
    const detail = buildToolTraceDetail(buildMessage({
      payloadJson: {
        tool_name: 'shell',
        status: 'waiting_for_approval',
        approval_id: 'approval-1',
        arguments: { command: 'git push origin feature/approveRunTime' },
      },
    }))

    expect(detail.approval).toEqual({
      runId: 'run-1',
      approvalId: 'approval-1',
    })
    expect(detail.approval).not.toHaveProperty('command')
    expect(detail.approval).not.toHaveProperty('arguments')

    const html = renderToStaticMarkup(
      <ToolTraceGroup
        status="waiting_for_approval"
        details={[detail]}
        onApprovalAction={approvalAction}
      />
    )

    expect(html).toContain('需要批准执行命令')
    expect(html).toContain('mb-8 max-w-[920px] mx-auto w-full')
    expect(html).toContain('允许一次')
    expect(html).toContain('拒绝')
    expect(html).toContain('flex-col')
    expect(html).not.toContain('border-l-4')
    expect(html).not.toContain('bg-amber')
  })

  // 场景：当消息缺少 runId 时，即使有 approvalId，也不应渲染批准/拒绝控件（缺少必要的关联信息）
  it('does not render approval controls without a run id and approval id', () => {
    const approvalAction = vi.fn()
    const detail = buildToolTraceDetail(buildMessage({
      runId: null,
      payloadJson: {
        tool_name: 'shell',
        status: 'waiting_for_approval',
        approval_id: 'approval-1',
        arguments: { command: 'git push origin feature/approveRunTime' },
      },
    }))

    const html = renderToStaticMarkup(
      <ToolTraceGroup
        status="waiting_for_approval"
        details={[detail]}
        onApprovalAction={approvalAction}
      />
    )

    expect(detail.approval).toBeUndefined()
    expect(html).not.toContain('aria-label="批准此操作"')
    expect(html).not.toContain('aria-label="拒绝此操作"')
  })

  // 场景（参数化）：轨迹一旦被批准（approved）或拒绝（denied），进入终态后就不应再显示批准/拒绝控件；
  // 同时验证详情状态和分组状态被正确映射为对应的终态（completed/cancelled）
  it.each([
    ['approved', 'success', 'completed'],
    ['denied', 'cancelled', 'cancelled'],
  ] as const)(
    'does not render approval controls after a trace is %s',
    (status, expectedDetailStatus, groupStatus) => {
      const approvalAction = vi.fn()
      const detail = buildToolTraceDetail(buildMessage({
        streamState: 'idle',
        payloadJson: {
          tool_name: 'shell',
          status,
          approval_id: 'approval-1',
          arguments: { command: 'git push origin feature/approveRunTime' },
        },
      }))

      const html = renderToStaticMarkup(
        <ToolTraceGroup
          status={groupStatus}
          details={[detail]}
          onApprovalAction={approvalAction}
        />
      )

      expect(detail.status).toBe(expectedDetailStatus)
      expect(detail.approval).toBeUndefined()
      expect(html).not.toContain('aria-label="批准此操作"')
      expect(html).not.toContain('aria-label="拒绝此操作"')
    }
  )

  // 场景：调用 sendApprovalAction 发送批准/拒绝动作时，传给回调的 payload 应精简为仅含 runId 和 approvalId，
  // 过滤掉 command 等展示用的额外字段，避免把不必要的数据发送到后端
  it('sends approve and deny approval actions with id-only payloads', () => {
    const approvalAction = vi.fn()
    const payload = {
      runId: 'run-1',
      approvalId: 'approval-1',
      command: 'git push origin feature/approveRunTime',
    }

    sendApprovalAction(approvalAction, 'approve', payload)
    sendApprovalAction(approvalAction, 'deny', payload)

    expect(approvalAction).toHaveBeenNthCalledWith(1, 'approve', {
      runId: 'run-1',
      approvalId: 'approval-1',
    })
    expect(approvalAction).toHaveBeenNthCalledWith(2, 'deny', {
      runId: 'run-1',
      approvalId: 'approval-1',
    })
  })
})

// 测试目标：WorkspaceTranscript（工作区会话转录组件）在各种消息类型/流式状态/滚动场景下的渲染行为
describe('WorkspaceTranscript conversation rendering', () => {
  // 场景：working_note（工作笔记）类型的助手消息默认应折叠显示，不直接暴露笔记原文
  it('collapses working-note assistant messages by default', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-working-note',
            role: 'assistant',
            messageType: 'assistant_message',
            displayMode: 'working_note',
            contentText: '你说得对，我先看一下当前实现。',
          }),
        ]}
      />
    )

    expect(html).toContain('展开过程')
    expect(html).not.toContain('你说得对，我先看一下当前实现。')
  })

  // 场景：较长的用户消息应在转录容器内自动换行显示，而不是在右侧边缘被裁剪
  it('wraps long user messages inside the transcript instead of clipping on the right edge', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-user',
            role: 'user',
            messageType: 'user_message',
            contentText: 'a'.repeat(160),
          }),
        ]}
      />
    )

    expect(html).toContain('max-w-[min(720px,calc(100%_-_16px))]')
    expect(html).toContain('break-words')
    expect(html).toContain('whitespace-pre-wrap')
  })

  // 场景：当助手输出仍在流式生成中时，不应重复触发转录条目的"进入动画"（避免视觉闪烁/重复播放动画）
  it('does not replay the transcript enter animation while assistant output is streaming', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-assistant',
            messageType: 'assistant_message',
            contentText: '正在输出',
            streamState: 'streaming',
          }),
        ]}
      />
    )

    expect(html).toContain('正在输出')
    expect(html).toContain('data-markdown-streaming="true"')
    expect(html).not.toContain('transcript-item-enter')
  })

  // 场景：tool_trace（工具调用轨迹）和 system_notice（系统通知）两种消息类型都能被正常渲染出来
  it('renders tool_trace and system_notice messages', () => {
    const toolTrace = buildMessage({
      id: 'msg-tool',
      messageType: 'tool_trace',
      payloadJson: {
        tool_name: 'shell',
        status: 'running',
      },
    })
    const systemNotice = buildMessage({
      id: 'msg-notice',
      role: 'system',
      runId: null,
      messageType: 'system_notice',
      payloadJson: { notice_code: 'run_cancelled' },
      contentText: '本次执行已取消',
    })

    const html = renderToStaticMarkup(
        <WorkspaceTranscript
          loaded
          configured
          currentProject={{
            id: 'project-1',
            name: 'ReflexionOS',
            path: '/tmp/reflexion',
            created_at: '2026-04-24T10:00:00Z',
            updated_at: '2026-04-24T10:00:00Z',
          }}
          currentSession={{
            id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[toolTrace, systemNotice]}
      />
    )

    expect(html).toContain('展开过程')
    expect(html).toContain('本次执行已取消')
  })

  // 场景：连续相邻的多个工具调用轨迹应被合并为一条时间线摘要（"展开过程"），具体的调用细节默认隐藏不直接展示
  it('groups adjacent tool traces into one timeline summary with hidden details', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-read',
            turnMessageIndex: 1,
            payloadJson: {
              tool_name: 'file',
              arguments: { action: 'read', path: '/tmp/reflexion/src/app.py' },
            },
          }),
          buildMessage({
            id: 'msg-search',
            turnMessageIndex: 2,
            createdAt: '2026-04-24T10:00:10Z',
            payloadJson: {
              tool_name: 'file',
              arguments: { action: 'search', query: 'conversation:event' },
            },
          }),
          buildMessage({
            id: 'msg-command',
            turnMessageIndex: 3,
            createdAt: '2026-04-24T10:00:20Z',
            payloadJson: {
              tool_name: 'shell',
              arguments: { command: 'git status --short' },
              output: ' M src/app.py',
            },
          }),
        ]}
      />
    )

    expect(html).toContain('展开过程')
    expect(html).not.toContain('探索 src/app.py')
    expect(html).not.toContain('搜索 &quot;conversation:event&quot;')
    expect(html).not.toContain('M src/app.py')
  })

  // 场景：当转录区域滚动位置离底部较远时，应显示"滚动到底部"按钮
  it('shows a scroll-to-bottom button when the transcript is away from the bottom', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[]}
      />
    )

    expect(html).toContain('滚动到底部')
  })

  // 场景：运行已启动但尚未开始流式输出内容时，应显示"等待模型响应"的思考中提示
  it('shows a thinking indicator while a run is active before streaming output starts', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[]}
        isRunning
      />
    )

    expect(html).toContain('等待模型响应')
  })

  // 场景：当存在 LLM 重试信息（retryInfo）时，应显示"重连"状态提示，而不是显示普通的"思考中"提示
  it('shows reconnect status instead of thinking while an LLM retry is pending', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[]}
        isRunning
        retryInfo={{
          error_type: 'APIConnectionError',
          attempt: 1,
          max_retries: 5,
          delay: 2,
          message: 'connection failed',
        }}
      />
    )

    expect(html).toContain('reconnect（1/5）')
    expect(html).toContain('2 秒后重试')
    expect(html).not.toContain('思考中')
    expect(html).not.toContain('请求失败')
  })

  // 场景：当消息携带 reasoning_text（推理文本）时，应在助手正文附近渲染一个轻量的"思考块"，默认折叠不直接展示推理内容
  it('renders a lightweight thinking block near assistant content when reasoning text exists', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-assistant',
            messageType: 'assistant_message',
            contentText: '最终回答',
            streamState: 'completed',
            payloadJson: {
              reasoning_text: '先检查项目结构',
            },
          }),
        ]}
        isRunning={false}
      />
    )

    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain('展开过程')
    expect(html).toContain('最终回答')
    expect(html).not.toContain('先检查项目结构')
  })

  // 场景：助手消息、思考块、系统提示等转录内容块应在阅读列（固定最大宽度）内居中显示
  it('centers assistant transcript blocks inside the reading column', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-assistant',
            messageType: 'assistant_message',
            contentText: '居中显示的助手回复',
            streamState: 'completed',
            payloadJson: {
              reasoning_text: '居中的思考块',
            },
          }),
          buildMessage({
            id: 'msg-notice',
            role: 'system',
            runId: null,
            messageType: 'system_notice',
            contentText: '居中的系统提示',
          }),
        ]}
      />
    )

    expect(html).toContain('max-w-[920px] mx-auto w-full text-[17px]')
    expect(html).toContain('mb-6 max-w-[920px] mx-auto w-full')
    expect(html).toContain('mt-1 flex w-full max-w-[920px]')
    expect(html).toContain('展开过程')
    expect(html).toContain('居中的系统提示')
  })

  // 场景：当用户已经产生过一次向上滚动交互（初次 startReached 被忽略）后，触发向上加载更多历史消息时，
  // 应使用 oldestLoadedTurnId（最早已加载轮次 ID）作为加载起点，而不是用某条具体消息 ID
  it('loads older turns from oldestLoadedTurnId after the initial startReached is ignored', () => {
    const loadMore = vi.fn()
    shouldInvokeStartReached = true

    renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-visible-oldest',
            role: 'user',
            messageType: 'user_message',
            contentText: '最早可见消息',
          }),
          buildMessage({
            id: 'msg-newest',
            messageType: 'assistant_message',
            contentText: '最新已加载消息',
            streamState: 'completed',
          }),
        ]}
        hasMore
        oldestLoadedTurnId="turn-7"
        onLoadMore={loadMore}
      />
    )

    expect(latestVirtuosoProps?.data?.[0]?.id).toBe('msg-visible-oldest')
    expect(loadMore).not.toHaveBeenCalled()
    latestVirtuosoProps?.startReached?.()
    expect(loadMore).toHaveBeenCalledTimes(1)
    expect(loadMore).toHaveBeenCalledWith('turn-7')
    expect(loadMore).not.toHaveBeenCalledWith('msg-visible-oldest')
  })

  // 场景：初次渲染、尚未发生任何向上滚动交互时，不应自动触发加载更多历史消息（避免刚进入页面就意外拉取历史）
  it('does not auto-load older turns on initial render before upward interaction', () => {
    const loadMore = vi.fn()
    shouldInvokeStartReached = true

    renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-visible-oldest',
            role: 'user',
            messageType: 'user_message',
            contentText: '最早可见消息',
          }),
        ]}
        hasMore
        oldestLoadedTurnId="turn-7"
        onLoadMore={loadMore}
      />
    )

    expect(loadMore).not.toHaveBeenCalled()
  })

  // 场景：向历史记录头部插入更多消息（前置追加）时，虚拟列表的 key 和 index 应保持稳定，从而不丢失滚动锚点位置
  it('passes stable virtual-list keys and indexes so prepended history keeps its scroll anchor', () => {
    renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-oldest',
            role: 'user',
            messageType: 'user_message',
            contentText: '最早已加载消息',
          }),
          buildMessage({
            id: 'msg-newest',
            messageType: 'assistant_message',
            contentText: '最新已加载消息',
            streamState: 'completed',
          }),
        ]}
        hasMore
        onLoadMore={vi.fn()}
      />
    )

    expect(latestVirtuosoProps?.firstItemIndex).toBe(999998)
    expect(latestVirtuosoProps?.computeItemKey?.(999998, latestVirtuosoProps.data?.[0] as TranscriptItem)).toBe('msg-oldest')
  })

  // 场景：判断"是否在底部"和"流式输出时是否跟随滚动"应统一使用 100px 作为底部阈值
  it('uses a 100px bottom threshold for button visibility and streaming follow', () => {
    renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-assistant',
            messageType: 'assistant_message',
            contentText: '正在回复',
            streamState: 'streaming',
          }),
        ]}
      />
    )

    expect(latestVirtuosoProps?.atBottomThreshold).toBe(100)
    expect(latestVirtuosoProps?.alignToBottom).toBe(true)
    expect(typeof latestVirtuosoProps?.followOutput).toBe('function')
    expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(true)).toBe(true)
    expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(false)).toBe(true)
  })

  // 场景：Virtuoso 虚拟列表滚动容器上必须携带用于测量的特定 DOM 属性（data-virtuoso-scroller 等），确保滚动测量逻辑正常工作
  it('forwards Virtuoso scroller DOM attributes required for measurement', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-oldest',
            role: 'user',
            messageType: 'user_message',
            contentText: '最早已加载消息',
          }),
        ]}
      />
    )

    expect(html).toContain('data-virtuoso-scroller="true"')
    expect(html).toContain('box-sizing:border-box')
  })

  // 场景：转录内容应保持在一个固定宽度的内层容器（frame）中，使右对齐的用户消息不会被外层滚动容器裁剪
  it('keeps transcript width on an inner frame so right-aligned user messages are not clipped by the scroller', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        bottomInset={220}
        messages={[
          buildMessage({
            id: 'msg-user',
            role: 'user',
            messageType: 'user_message',
            contentText: '一条很长的用户消息，应该在内容框内右对齐并自动换行，不应该被右侧滚动容器裁剪。',
          }),
        ]}
      />
    )

    expect(html).toContain('data-transcript-frame="true"')
    expect(html).toContain('max-width:1280px')
    expect(html).toContain('data-transcript-bottom-spacer="true"')
    expect(html).toContain('height:236px')
    expect(html).not.toContain('padding-bottom:268px')
    expect(html).not.toContain('overflow-x:hidden;max-width:1280px')
  })

  // 场景：当推理文本（reasoning_text）仍在流式生成中时，思考块应保持展开状态，不应显示加载旋转动效
  it('keeps the thinking block expanded while reasoning is still streaming', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-assistant',
            messageType: 'assistant_message',
            contentText: '',
            streamState: 'streaming',
            payloadJson: {
              reasoning_text: '先检查项目结构\n再看错误点',
            },
          }),
        ]}
        isRunning
      />
    )

    expect(html).toContain('Thinking')
    expect(html).toContain('先检查项目结构')
    expect(html).toContain('aria-expanded="true"')
    expect(html).not.toContain('animate-spin')
  })

  // 场景：当工具调用轨迹处于活跃状态但没有推理文本时，应回退展示 runtimeStatus 提供的"正在执行工具"状态提示
  it('shows executing-tool fallback status when tool traces are active without reasoning text', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-tool',
            messageType: 'tool_trace',
            streamState: 'idle',
            payloadJson: {
              tool_name: 'shell',
              status: 'running',
            },
          }),
        ]}
        isRunning
        runtimeStatus={{ kind: 'executing_tool', label: '正在执行工具' }}
      />
    )

    expect(html).toContain('正在执行工具')
    expect(html).toContain('mb-8 mx-auto flex w-full max-w-[920px]')
    expect(html).toContain('data-running-bars="true"')
    expect(html).toContain('data-running-bar="1"')
    expect(html).toContain('data-running-bar="2"')
    expect(html).toContain('data-running-bar="3"')
  })

  // 场景：即使助手输出已经在流式生成中，只要存在重试信息（retryInfo），也应同时显示"重连"状态提示
  it('shows reconnect status while assistant output is already streaming', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-assistant',
            messageType: 'assistant_message',
            contentText: '正在回复',
            streamState: 'streaming',
          }),
        ]}
        isRunning
        retryInfo={{
          error_type: 'APIConnectionError',
          attempt: 1,
          max_retries: 5,
          delay: 2,
          message: 'connection failed',
        }}
      />
    )

    expect(html).toContain('正在回复')
    expect(html).toContain('reconnect（1/5）')
    expect(html).toContain('2 秒后重试')
    expect(html).not.toContain('请求失败')
  })

  // 场景：计划面板（plan panel）应作为一个居中的粘性（sticky）清单，展示在输入区域上方
  it('renders the plan panel as a centered sticky checklist above the input area', () => {
    const html = renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-assistant',
            messageType: 'assistant_message',
            contentText: '我会先处理这个问题。',
            streamState: 'completed',
          }),
        ]}
        isRunning
        plan={{
          goal: '修复计划显示',
          steps: [
            { content: '定位问题', status: 'completed', findings: '' },
            { content: '修改实现', status: 'in_progress', findings: '' },
            { content: '验证结果', status: 'pending', findings: '' },
          ],
        }}
      />
    )

    expect(html).toContain('我会先处理这个问题。')
    expect(html).toContain('共 3 个任务，已完成 1 个')
    expect(html).toContain('sticky')
    expect(html).toContain('mx-auto')
    expect(html).not.toContain('right-6')
    expect(html).not.toContain('思考中')
  })

  // 场景：验证内部工具函数 getRetryCountdownSeconds 能根据已经过去的时间正确地从重试延迟倒数到 0
  it('counts retry delay down from the retry delay to zero', async () => {
    const module = await import('../WorkspaceTranscript') as unknown as {
      getRetryCountdownSeconds?: (delay: number, elapsedMs?: number) => number
    }

    expect(typeof module.getRetryCountdownSeconds).toBe('function')
    expect(module.getRetryCountdownSeconds?.(2, 0)).toBe(2)
    expect(module.getRetryCountdownSeconds?.(2, 1_000)).toBe(1)
    expect(module.getRetryCountdownSeconds?.(2, 2_000)).toBe(0)
    expect(module.getRetryCountdownSeconds?.(2, 3_000)).toBe(0)
  })

  // 场景：验证内部工具函数 getNextFirstItemIndex 只在"历史消息被前置追加"时才偏移虚拟列表的首项索引，其余情况保持不变
  it('only shifts the virtual first item index when history is prepended', async () => {
    const module = await import('../WorkspaceTranscript') as unknown as {
      getNextFirstItemIndex?: (
        previous: null | {
          sessionId: string | null
          firstItemId: string | null
          lastItemId: string | null
          itemCount: number
          firstItemIndex: number
        },
        next: {
          sessionId: string | null
          firstItemId: string | null
          lastItemId: string | null
          itemCount: number
        }
      ) => number
    }

    expect(typeof module.getNextFirstItemIndex).toBe('function')
    const initialIndex = module.getNextFirstItemIndex?.(null, {
      sessionId: 'session-1',
      firstItemId: 'msg-2',
      lastItemId: 'msg-3',
      itemCount: 2,
    })

    expect(initialIndex).toBe(999998)
    expect(module.getNextFirstItemIndex?.({
      sessionId: 'session-1',
      firstItemId: 'msg-2',
      lastItemId: 'msg-3',
      itemCount: 2,
      firstItemIndex: initialIndex ?? 0,
    }, {
      sessionId: 'session-1',
      firstItemId: 'msg-2',
      lastItemId: 'msg-4',
      itemCount: 3,
    })).toBe(initialIndex)
    expect(module.getNextFirstItemIndex?.({
      sessionId: 'session-1',
      firstItemId: 'msg-2',
      lastItemId: 'msg-3',
      itemCount: 2,
      firstItemIndex: initialIndex ?? 0,
    }, {
      sessionId: 'session-1',
      firstItemId: 'msg-1',
      lastItemId: 'msg-3',
      itemCount: 3,
    })).toBe(999997)
  })

  // 场景：验证内部工具函数 getTranscriptBottomPadding 能根据测量到的输入区安全高度（bottomInset）计算出转录区应留的底部内边距
  it('computes transcript bottom padding from the measured input safe area', async () => {
    const module = await import('../WorkspaceTranscript') as unknown as {
      getTranscriptBottomPadding?: (bottomInset: number) => number
    }

    expect(typeof module.getTranscriptBottomPadding).toBe('function')
    expect(module.getTranscriptBottomPadding?.(220)).toBe(236)
    expect(module.getTranscriptBottomPadding?.(80)).toBe(96)
  })

  // 场景：验证 shouldMarkUserScrolledAway / shouldForceBottomOnNewUserMessage / shouldForceBottomAfterUserAppend 三个工具函数，
  // 能正确区分"用户主动滚动离开底部"和"流式渲染引起的测量抖动"，并在合适时机强制滚回底部
  it('distinguishes user scroll intent from streaming measurement jitter', async () => {
    const module = await import('../WorkspaceTranscript') as unknown as {
      shouldMarkUserScrolledAway?: (position: {
        userScrollIntent: boolean
        distanceFromBottom: number
      }) => boolean
      shouldForceBottomOnNewUserMessage?: (wasUserScrolledAway: boolean) => boolean
      shouldForceBottomAfterUserAppend?: (position: {
        previousLastUserMessageId: string | null
        nextLastUserMessageId: string | null
        wasUserScrolledAway: boolean
      }) => boolean
    }

    expect(typeof module.shouldMarkUserScrolledAway).toBe('function')
    expect(module.shouldMarkUserScrolledAway?.({
      userScrollIntent: false,
      distanceFromBottom: 360,
    })).toBe(false)
    expect(module.shouldMarkUserScrolledAway?.({
      userScrollIntent: true,
      distanceFromBottom: 360,
    })).toBe(true)
    expect(module.shouldMarkUserScrolledAway?.({
      userScrollIntent: false,
      distanceFromBottom: 40,
    })).toBe(false)
    expect(typeof module.shouldForceBottomOnNewUserMessage).toBe('function')
    expect(module.shouldForceBottomOnNewUserMessage?.(false)).toBe(false)
    expect(module.shouldForceBottomOnNewUserMessage?.(true)).toBe(true)
    expect(typeof module.shouldForceBottomAfterUserAppend).toBe('function')
    expect(module.shouldForceBottomAfterUserAppend?.({
      previousLastUserMessageId: 'msg-user-1',
      nextLastUserMessageId: 'msg-user-2',
      wasUserScrolledAway: false,
    })).toBe(false)
    expect(module.shouldForceBottomAfterUserAppend?.({
      previousLastUserMessageId: 'msg-user-1',
      nextLastUserMessageId: 'msg-user-2',
      wasUserScrolledAway: true,
    })).toBe(true)
    expect(module.shouldForceBottomAfterUserAppend?.({
      previousLastUserMessageId: 'msg-user-2',
      nextLastUserMessageId: 'msg-user-2',
      wasUserScrolledAway: true,
    })).toBe(false)
  })

  // 场景：追加新消息（messages 数组变化）时，传给 Virtuoso 的 components 对象引用应保持稳定，避免不必要的重渲染
  it('keeps the Virtuoso components object stable when messages append', () => {
    renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-user-1',
            role: 'user',
            messageType: 'user_message',
            contentText: '第一条',
          }),
        ]}
      />
    )
    const firstComponents = latestVirtuosoProps?.components

    renderToStaticMarkup(
      <WorkspaceTranscript
        loaded
        configured
        currentProject={{
          id: 'project-1',
          name: 'ReflexionOS',
          path: '/tmp/reflexion',
          created_at: '2026-04-24T10:00:00Z',
          updated_at: '2026-04-24T10:00:00Z',
        }}
        currentSession={{
          id: 'session-1',
          projectId: 'project-1',
          title: '会话',
          agentMode: 'build',
          lastEventSeq: 0,
          activeTurnId: null,
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[
          buildMessage({
            id: 'msg-user-1',
            role: 'user',
            messageType: 'user_message',
            contentText: '第一条',
          }),
          buildMessage({
            id: 'msg-user-2',
            role: 'user',
            messageType: 'user_message',
            contentText: '第二条',
            turnMessageIndex: 2,
          }),
        ]}
      />
    )

    expect(latestVirtuosoProps?.components).toBe(firstComponents)
  })
})
