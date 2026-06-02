import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import AgentWorkspace from './AgentWorkspace'

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
  WorkspaceTranscript: () => <div data-workspace-transcript="true" />,
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

vi.mock('@/features/conversation/conversationStore', () => ({
  useConversationStore: (selector: (state: unknown) => unknown) => selector({
    agentModeBySessionId: { 'session-1': 'build' },
    conversationsBySessionId: { 'session-1': { runsById: {} } },
  }),
}))

vi.mock('@/features/code/codeTabStore', () => ({
  useCodeTabStore: (selector: (state: unknown) => unknown) => selector({
    workspaceTab: 'chat',
    setSidebarOpen: vi.fn(),
    openFile: vi.fn(),
  }),
}))

vi.mock('@/features/terminal/terminalStore', () => ({
  useTerminalStore: (selector: (state: unknown) => unknown) => selector({
    togglePanel: vi.fn(),
    createTerminal: vi.fn(),
  }),
}))

vi.mock('@/stores/workspaceStore', () => ({
  useWorkspaceStore: (selector: (state: unknown) => unknown) => selector({
    currentSessionId: 'session-1',
  }),
}))

vi.mock('@/stores/projectStore', () => ({
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
})
