import { createRef } from 'react'
import type { HTMLAttributes, ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { ConversationMessage } from '@/types/conversation'
import { ToolTraceCard } from './ToolTraceCard'
import { WorkspaceTranscript } from './WorkspaceTranscript'

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children?: ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: HTMLAttributes<HTMLDivElement> & { children?: ReactNode }) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: HTMLAttributes<HTMLSpanElement> & { children?: ReactNode }) => <span {...props}>{children}</span>,
  },
}))

vi.mock('@/components/animations/SlideIn', () => ({
  SlideIn: ({ children }: { children?: ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/chat/MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => <div>{content}</div>,
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

    expect(html).toContain('探索 src/app.py')
    expect(html).not.toContain('action')
    expect(html).not.toContain('hello')
  })
})

describe('WorkspaceTranscript conversation rendering', () => {
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
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[toolTrace, systemNotice]}
        messagesEndRef={createRef<HTMLDivElement>()}
      />
    )

    expect(html).toContain('运行命令')
    expect(html).toContain('本次执行已取消')
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
          createdAt: '2026-04-24T10:00:00Z',
          updatedAt: '2026-04-24T10:00:00Z',
        }}
        messages={[]}
        isRunning
        messagesEndRef={createRef<HTMLDivElement>()}
      />
    )

    expect(html).toContain('思考中')
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
        messagesEndRef={createRef<HTMLDivElement>()}
      />
    )

    expect(html).toContain('reconnect（1/5）')
    expect(html).toContain('2 秒后重试')
    expect(html).not.toContain('思考中')
    expect(html).not.toContain('请求失败')
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
        messagesEndRef={createRef<HTMLDivElement>()}
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
          current_step_index: 1,
          steps: [
            { id: 1, description: '定位问题', status: 'completed', findings: '' },
            { id: 2, description: '修改实现', status: 'in_progress', findings: '' },
            { id: 3, description: '验证结果', status: 'pending', findings: '' },
          ],
        }}
        messagesEndRef={createRef<HTMLDivElement>()}
      />
    )

    expect(html).toContain('我会先处理这个问题。')
    expect(html).toContain('共 3 个任务，已经完成 1 个')
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
})
