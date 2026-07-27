/**
 * AgentWorkspace 页面布局测试：验证 ChatInput 居中、对话记录底部安全距离、
 * 代码面板收起时宽度归零等核心布局行为。
 * 使用 renderToStaticMarkup 进行服务端渲染式快照检验，无需 DOM 交互。
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import AgentWorkspace from '../AgentWorkspace'

let latestTranscriptProps: Record<string, unknown> | null = null

vi.mock('@/components/chat/ChatInput', () => ({
  ChatInput: () => <div data-chat-input="true" />,
}))

vi.mock('@/components/workspace/CodeTab', () => ({
  CodeTab: () => <div />,
}))

vi.mock('@/components/workspace/PlanProgress', () => ({
  PlanMinimizedBar: () => <div data-plan-minimized="true" />,
}))

vi.mock('@/components/workspace/WorkspaceHeader', () => ({
  WorkspaceHeader: () => <div />,
}))

vi.mock('@/components/workspace/WorkspaceTranscript', () => ({
  WorkspaceTranscript: (props: Record<string, unknown>) => {
    latestTranscriptProps = props
    return <div data-workspace-transcript="true" data-bottom-inset={String(props.bottomInset)} />
  },
}))

vi.mock('@/components/terminal/TerminalPanel', () => ({
  TerminalPanel: () => <div />,
}))

vi.mock('@/components/common/Toast', () => ({
  ToastContainer: () => <div />,
}))

vi.mock('@/components/workspace/FileSidebar', () => ({
  FileSidebar: () => <div />,
}))

vi.mock('@/features/conversation/stores/conversation.store', () => ({
  useConversationStore: (selector: (state: unknown) => unknown) => selector({
    agentModeBySessionId: { 'session-1': 'build' },
    conversationsBySessionId: { 'session-1': { runsById: {} } },
  }),
}))

vi.mock('@/features/code/stores/codeTab.store', () => ({
  useCodeTabStore: (selector: (state: unknown) => unknown) => selector({
    codePanelOpen: false,
    codePanelWidth: 480,
    sidebarOpen: false,
    sidebarWidth: 240,
    setSidebarOpen: vi.fn(),
    setCodePanelWidth: vi.fn(),
    openFile: vi.fn(),
  }),
}))

vi.mock('@/features/terminal/stores/terminal.store', () => ({
  useTerminalStore: (selector: (state: unknown) => unknown) => selector({
    togglePanel: vi.fn(),
    createTerminal: vi.fn(),
  }),
}))

vi.mock('@/features/workspace/stores/workspace.store', () => ({
  useWorkspaceStore: (selector: (state: unknown) => unknown) => selector({
    currentSessionId: 'session-1',
  }),
}))

vi.mock('@/features/projects/stores/project.store', () => ({
  useProjectStore: (selector: (state: unknown) => unknown) => selector({
    currentProject: { path: '/tmp/reflexion' },
  }),
}))

vi.mock('@/hooks/useConversationData', () => ({
  useConversationData: () => ({
    messages: [],
    isRunning: false,
    plan: null,
    hasMore: false,
    oldestLoadedTurnId: null,
  }),
}))

vi.mock('@/hooks/useConversationRuntime', () => ({
  useConversationRuntime: () => ({
    connectionStatus: 'connected',
    isCancelling: false,
    retryInfo: null,
    startTurn: vi.fn(),
    cancelRun: vi.fn(),
    approveTool: vi.fn(),
    denyTool: vi.fn(),
    trustTool: vi.fn(),
    editAndRerun: vi.fn(),
    setMode: vi.fn(),
    resetConversationRuntime: vi.fn(),
    loadMore: vi.fn(),
  }),
}))

vi.mock('@/hooks/useCurrentSessionViewModel', () => ({
  useCurrentSessionViewModel: () => ({
    currentProject: { id: 'project-1' },
    currentSession: { id: 'session-1' },
    configured: true,
    loaded: true,
    selection: { providerId: null, modelId: null },
    headerProps: {},
    transcriptProps: {},
    inputProps: {},
  }),
}))

vi.mock('@/hooks/useSendMessage', () => ({
  useSendMessage: () => ({ sendMessage: vi.fn() }),
}))

describe('AgentWorkspace', () => {
  it('centers the chat input in the same width frame as the transcript', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)

    expect(html).toContain('data-chat-input-frame="true"')
    expect(html).toContain('max-w-[1280px]')
    expect(html).toContain('mx-auto')
    expect(html).toContain('data-chat-input="true"')
  })

  it('passes a bottom safe area to the transcript before measurement completes', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)

    expect(latestTranscriptProps?.bottomInset).toBe(80)
    expect(html).toContain('data-bottom-inset="80"')
  })

  it('always renders the chat transcript regardless of codePanelOpen', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)
    expect(html).toContain('data-workspace-transcript="true"')
  })

  it('collapses the code panel container to zero width when codePanelOpen is false', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)
    expect(html).toContain('data-code-panel="true"')
    expect(html).toMatch(/data-code-panel="true"[^>]*style="[^"]*width:\s*0/)
  })
})
