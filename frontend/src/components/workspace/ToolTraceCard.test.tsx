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
    messageIndex: 1,
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
  it('renders tool metadata and output payload', () => {
    const html = renderToStaticMarkup(
      <ToolTraceCard
        message={buildMessage({
          payloadJson: {
            tool_name: 'shell',
            status: 'completed',
            arguments: { command: 'echo hello' },
            output: 'hello',
            duration: 120,
          },
        })}
      />
    )

    expect(html).toContain('shell')
    expect(html).toContain('completed')
    expect(html).toContain('echo hello')
    expect(html).toContain('hello')
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

    expect(html).toContain('shell')
    expect(html).toContain('本次执行已取消')
  })
})
