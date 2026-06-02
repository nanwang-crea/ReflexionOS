import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { sendApprovalAction } from '@/components/execution/approvalActions'
import type { ConversationMessage } from '@/types/conversation'
import { ToolTraceCard, ToolTraceGroup } from './ToolTraceCard'
import { WorkspaceTranscript } from './WorkspaceTranscript'
import { buildToolTraceDetail, type TranscriptItem } from './transcriptItems'

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
}

let latestVirtuosoProps: MockVirtuosoProps | null = null

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement> & { children?: React.ReactNode }) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: React.HTMLAttributes<HTMLSpanElement> & { children?: React.ReactNode }) => <span {...props}>{children}</span>,
    button: ({ children, ...props }: React.HTMLAttributes<HTMLButtonElement> & { children?: React.ReactNode }) => <button {...props}>{children}</button>,
  },
}))

vi.mock('react-virtuoso', () => {
  return {
    Virtuoso: (props: MockVirtuosoProps) => {
      latestVirtuosoProps = props
      const { data, itemContent, components, atBottomStateChange, startReached } = props
      const isAtBottom = Boolean(data && data.length > 0)
      if (atBottomStateChange) atBottomStateChange(isAtBottom)
      if (startReached) startReached()
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

vi.mock('@/components/chat/MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content, className }: { content: string; className?: string }) => (
    <div className={className}>{content}</div>
  ),
}))

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

describe('ToolTraceCard', () => {
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

describe('WorkspaceTranscript conversation rendering', () => {
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

    expect(html).toContain('过程说明')
    expect(html).not.toContain('你说得对，我先看一下当前实现。')
  })

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

    expect(html).toContain('已运行 1 条命令')
    expect(html).toContain('本次执行已取消')
  })

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

    expect(html).toContain('已探索 1 个文件，已探索 1 次搜索，已运行 1 条命令')
    expect(html).not.toContain('探索 src/app.py')
    expect(html).not.toContain('搜索 &quot;conversation:event&quot;')
    expect(html).not.toContain('M src/app.py')
  })

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

    expect(html).toContain('Thinking')
    expect(html).toContain('先检查项目结构')
    expect(html).toContain('aria-expanded="false"')
  })

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
    expect(html).toContain('mb-3 max-w-[920px] mx-auto w-full')
    expect(html).toContain('mb-6 max-w-[920px] mx-auto w-full')
    expect(html).toContain('mt-1 mx-auto flex w-full max-w-[920px]')
    expect(html).toContain('居中的思考块')
    expect(html).toContain('居中的系统提示')
  })

  it('loads older messages when the virtualized transcript reaches the start', () => {
    const loadMore = vi.fn()

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
        onLoadMore={loadMore}
      />
    )

    expect(loadMore).toHaveBeenCalledTimes(1)
    expect(loadMore).toHaveBeenCalledWith('msg-oldest')
  })

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
    expect(typeof latestVirtuosoProps?.followOutput).toBe('function')
    expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(true)).toBe('smooth')
    expect((latestVirtuosoProps?.followOutput as (isAtBottom: boolean) => boolean | 'smooth')(false)).toBe(false)
  })

  it('autoscrolls streaming content growth only when the user was already at the bottom', async () => {
    const module = await import('./WorkspaceTranscript') as unknown as {
      shouldAutoscrollTranscriptChange?: (
        previous: { sessionId: string | null; tailKey: string | null } | null,
        next: { sessionId: string | null; tailKey: string | null },
        wasAtBottom: boolean
      ) => boolean
    }

    expect(typeof module.shouldAutoscrollTranscriptChange).toBe('function')
    expect(module.shouldAutoscrollTranscriptChange?.(
      { sessionId: 'session-1', tailKey: 'msg-2:streaming:short' },
      { sessionId: 'session-1', tailKey: 'msg-2:streaming:longer' },
      true
    )).toBe(true)
    expect(module.shouldAutoscrollTranscriptChange?.(
      { sessionId: 'session-1', tailKey: 'msg-2:streaming:short' },
      { sessionId: 'session-1', tailKey: 'msg-2:streaming:longer' },
      false
    )).toBe(false)
    expect(module.shouldAutoscrollTranscriptChange?.(
      { sessionId: 'session-1', tailKey: 'msg-2:streaming:short' },
      { sessionId: 'session-2', tailKey: 'msg-2:streaming:longer' },
      true
    )).toBe(false)
  })

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
  })

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
          currentStepIndex: 1,
          steps: [
            { id: 1, description: '定位问题', status: 'completed' },
            { id: 2, description: '修改实现', status: 'in_progress' },
            { id: 3, description: '验证结果', status: 'pending' },
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

  it('counts retry delay down from the retry delay to zero', async () => {
    const module = await import('./WorkspaceTranscript') as unknown as {
      getRetryCountdownSeconds?: (delay: number, elapsedMs?: number) => number
    }

    expect(typeof module.getRetryCountdownSeconds).toBe('function')
    expect(module.getRetryCountdownSeconds?.(2, 0)).toBe(2)
    expect(module.getRetryCountdownSeconds?.(2, 1_000)).toBe(1)
    expect(module.getRetryCountdownSeconds?.(2, 2_000)).toBe(0)
    expect(module.getRetryCountdownSeconds?.(2, 3_000)).toBe(0)
  })

  it('only shifts the virtual first item index when history is prepended', async () => {
    const module = await import('./WorkspaceTranscript') as unknown as {
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
})
