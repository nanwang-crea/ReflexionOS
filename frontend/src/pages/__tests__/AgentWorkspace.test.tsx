/**
 * 文件功能：AgentWorkspace 页面布局测试
 * 文件描述：验证 ChatInput 居中、对话记录底部安全距离、代码面板收起时宽度归零等核心布局行为。
 *          使用 renderToStaticMarkup 进行服务端渲染式快照检验，无需 DOM 交互
 * 核心逻辑：通过 vi.mock 将 AgentWorkspace 依赖的所有子组件、store、hook 替换为最小可控的
 *          假实现，只保留布局相关的关键 DOM 属性（如 data-* 标记），从而在不依赖真实业务逻辑
 *          的情况下，专注断言布局结构是否符合预期
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import AgentWorkspace from '../AgentWorkspace'

/** 记录 WorkspaceTranscript 组件最近一次收到的 props，供测试用例断言 bottomInset 等字段 */
let latestTranscriptProps: Record<string, unknown> | null = null

// 以下 vi.mock 调用将 AgentWorkspace 依赖的子组件替换为极简占位组件，
// 仅保留测试需要断言的 data-* 属性，避免真实子组件的复杂渲染逻辑影响测试
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

// WorkspaceTranscript 的假实现额外把收到的 props 存入 latestTranscriptProps，
// 便于测试用例断言 bottomInset 是否被正确传递
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

// 以下各 vi.mock 分别对应 AgentWorkspace 依赖的各个 zustand store 的假实现，
// 均通过传入的 selector 函数从固定的假状态对象中取值，模拟 zustand 的选择器用法
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
  /**
   * 测试名：centers the chat input in the same width frame as the transcript
   * 功能：验证聊天输入框与对话记录容器共用同一个宽度约束（max-w-[1280px] + mx-auto），
   *      从而保证两者在页面上视觉居中对齐
   * 断言逻辑：渲染 AgentWorkspace 后检查输出 HTML 是否同时包含 data-chat-input-frame 标记、
   *          max-w-[1280px] 和 mx-auto 类名，以及 ChatInput 假组件渲染出的标记
   */
  it('centers the chat input in the same width frame as the transcript', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)

    expect(html).toContain('data-chat-input-frame="true"')
    expect(html).toContain('max-w-[1280px]')
    expect(html).toContain('mx-auto')
    expect(html).toContain('data-chat-input="true"')
  })

  /**
   * 测试名：passes a bottom safe area to the transcript before measurement completes
   * 功能：验证在 ChatInput 高度尚未测量完成前，会传给 WorkspaceTranscript 一个兜底的
   *      底部安全距离（CHAT_INPUT_FALLBACK_INSET_PX = 80px），避免内容被输入框遮挡
   * 断言逻辑：渲染后检查 WorkspaceTranscript 假组件收到的 bottomInset props 是否为 80，
   *          以及渲染出的 data-bottom-inset 属性是否为 "80"
   */
  it('passes a bottom safe area to the transcript before measurement completes', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)

    expect(latestTranscriptProps?.bottomInset).toBe(80)
    expect(html).toContain('data-bottom-inset="80"')
  })

  /**
   * 测试名：always renders the chat transcript regardless of codePanelOpen
   * 功能：验证对话记录区域始终渲染，不受代码面板是否展开（codePanelOpen）的影响
   * 断言逻辑：在当前 mock 配置（codePanelOpen: false）下渲染，检查输出中仍包含
   *          data-workspace-transcript 标记
   */
  it('always renders the chat transcript regardless of codePanelOpen', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)
    expect(html).toContain('data-workspace-transcript="true"')
  })

  /**
   * 测试名：collapses the code panel container to zero width when codePanelOpen is false
   * 功能：验证代码面板容器在收起状态（codePanelOpen 为 false）下宽度被设置为 0，
   *      而不是从 DOM 中卸载（保留内部编辑器状态）
   * 断言逻辑：检查输出中存在 data-code-panel 标记，且其内联 style 中的 width 值为 0
   */
  it('collapses the code panel container to zero width when codePanelOpen is false', () => {
    const html = renderToStaticMarkup(<AgentWorkspace />)
    expect(html).toContain('data-code-panel="true"')
    expect(html).toMatch(/data-code-panel="true"[^>]*style="[^"]*width:\s*0/)
  })
})
