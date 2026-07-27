/**
 * AgentWorkspace 页面：主工作区布局。
 * 左侧对话区（常驻，flex-1）+ 右侧代码面板（可折叠，宽度可拖拽调整）+ 文件树侧边栏（代码面板展开时显示）。
 * 键盘快捷键：Ctrl+` 切换终端、Ctrl+Shift+` 新建终端、Tab 切换 agent 模式（非输入框时）。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatInput } from '@/components/chat/ChatInput'
import { CodeTab } from '@/components/workspace/CodeTab'
import { PlanMinimizedBar } from '@/components/workspace/PlanProgress'
import { WorkspaceHeader } from '@/components/workspace/WorkspaceHeader'
import { WorkspaceTranscript } from '@/components/workspace/WorkspaceTranscript'
import { TerminalPanel } from '@/components/terminal/TerminalPanel'
import { useConversationStore } from '@/features/conversation/stores/conversation.store'
import { useCodeTabStore } from '@/features/code/stores/codeTab.store'
import { useTerminalStore } from '@/features/terminal/stores/terminal.store'
import { useConversationData } from '@/hooks/useConversationData'
import { useConversationRuntime } from '@/hooks/useConversationRuntime'
import { useSessionUnreadState } from '@/hooks/useSessionUnreadState'
import { useCurrentSessionViewModel } from '@/hooks/useCurrentSessionViewModel'
import { useSendMessage } from '@/hooks/useSendMessage'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'
import { useProjectStore } from '@/features/projects/stores/project.store'
import { useImageUpload } from '@/features/conversation/hooks/useImageUpload'
import { supportsVision } from '@/constants/visionModels'
import { useToastStore } from '@/shared/stores/toast.store'
import { nativeDialogService } from '@/services/dialogService'
import { FileSidebar } from '@/components/workspace/FileSidebar'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
import type { AgentMode } from '@/types/conversation'

// 对话记录区底部安全距离（px），在 ChatInput 高度测量完成前作为占位值防止内容被遮挡
const CHAT_INPUT_FALLBACK_INSET_PX = 80

/**
 * AgentWorkspace 主页面组件。
 * 输出：完整的工作区布局 JSX，包含 Header、对话记录、输入框、代码面板和文件树。
 */
export default function AgentWorkspace() {
  const currentSessionId = useWorkspaceStore((state) => state.currentSessionId)
  const {
    connectionStatus,
    isCancelling,
    retryInfo,
    startTurn,
    cancelRun,
    approveTool,
    denyTool,
    trustTool,
    editAndRerun,
    setMode,
    resetConversationRuntime,
    loadMore,
  } = useConversationRuntime(currentSessionId)
  const { messages, isRunning, plan, hasMore, oldestLoadedTurnId } = useConversationData(currentSessionId)
  // 当前会话被查看时，持续把已读基线追到最新，使其不累积未读；离开后再增长的事件才算未读。
  useSessionUnreadState(currentSessionId)
  const agentMode: AgentMode = useConversationStore(
    (s) => currentSessionId ? s.agentModeBySessionId[currentSessionId] ?? 'build' : 'build'
  )
  const runsById = useConversationStore((s) =>
    currentSessionId ? s.conversationsBySessionId[currentSessionId]?.runsById : undefined
  )
  const [isPlanMinimized, setIsPlanMinimized] = useState(false)
  const codePanelOpen = useCodeTabStore((s) => s.codePanelOpen)
  const codePanelWidth = useCodeTabStore((s) => s.codePanelWidth)
  const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)
  const setCodePanelWidth = useCodeTabStore((s) => s.setCodePanelWidth)
  const openFile = useCodeTabStore((s) => s.openFile)
  const togglePanel = useTerminalStore((s) => s.togglePanel)
  const createTerminal = useTerminalStore((s) => s.createTerminal)
  const currentProject = useProjectStore((s) => s.currentProject)

  /**
   * 切换 Agent 模式（build/plan），运行中不允许切换。
   */
  const toggleMode = useCallback(() => {
    if (!currentSessionId || isRunning) return
    const newMode: AgentMode = agentMode === 'build' ? 'plan' : 'build'
    setMode(newMode)
  }, [currentSessionId, agentMode, isRunning, setMode])

  /**
   * 重置对话：破坏性操作，先弹二次确认对话框再执行（先停后清，不可恢复）。
   */
  const handleReset = useCallback(async () => {
    if (!currentSessionId) return
    const confirmed = await nativeDialogService.confirmAction(
      '确定要清空当前会话的全部对话记录吗？此操作不可恢复。',
      { variant: 'danger' }
    )
    if (!confirmed) return
    void resetConversationRuntime()
  }, [currentSessionId, resetConversationRuntime])

  // 注册全局键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '`' && e.ctrlKey && !e.shiftKey) {
        e.preventDefault()
        togglePanel()
      }
      if (e.key === '`' && e.ctrlKey && e.shiftKey) {
        e.preventDefault()
        const cwd = currentProject?.path ?? ''
        createTerminal(cwd)
      }
      // Tab 键切换 agent 模式，仅在焦点不在输入框时触发
      if (e.key === 'Tab' && !e.ctrlKey && !e.shiftKey && !e.metaKey) {
        if (!(e.target instanceof HTMLElement)) return
        if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return
        e.preventDefault()
        toggleMode()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [togglePanel, createTerminal, currentProject, toggleMode])

  // 代码面板开关与文件树 sidebarOpen 保持联动（关闭代码面板时同步关闭文件树）
  useEffect(() => {
    setSidebarOpen(codePanelOpen)
  }, [codePanelOpen, setSidebarOpen])

  /**
   * 点击执行详情（ActionReceiptDetail）时，自动在代码面板打开对应文件。
   * edit/create/delete 类操作用 diff 视图，其他用 edit 视图。
   * 输入：detail（操作详情，包含 arguments.path 和 category）
   */
  const handleDetailClick = useCallback((detail: ActionReceiptDetail) => {
    const args = detail.arguments
    if (!args || typeof args !== 'object') return
    const path = typeof args.path === 'string' ? args.path : undefined
    if (!path) return
    const viewMode = ['edit', 'create', 'delete'].includes(detail.category) ? 'diff' : 'edit'
    openFile(path, viewMode)
  }, [openFile])

  // plan 消失（run 结束）时重置最小化状态，确保下次 plan 出现时展开显示
  const effectivePlanMinimized = plan ? isPlanMinimized : false

  const viewModel = useCurrentSessionViewModel({
    messages,
    isRunning,
    isCancelling,
    connectionStatus,
    retryInfo,
    plan,
    hasMore,
    onLoadMore: currentSessionId ? (beforeTurnId) => loadMore(currentSessionId, beforeTurnId) : undefined,
    onReset: handleReset,
    editAndRerun,
    onApprovalAction: (action, payload) => {
      if (action === 'approve') {
        approveTool(payload.runId, payload.approvalId, payload.parentSessionId)
        return
      }
      if (action === 'trust') {
        trustTool(payload.runId, payload.approvalId, payload.parentSessionId)
        return
      }
      denyTool(payload.runId, payload.approvalId, payload.parentSessionId)
    },
  })
  const { sendMessage } = useSendMessage({
    currentSession: viewModel.currentSession,
    configured: viewModel.configured,
    selection: viewModel.selection,
    startTurn,
  })

  const {
    attachments,
    addFiles,
    removeAttachment,
    clearAttachments,
    uploadAll,
  } = useImageUpload(currentSessionId ?? null)

  /**
   * 添加图片附件：若当前模型不支持视觉，展示提示 toast。
   * 输入：files（File 数组）
   */
  const handleImageAdd = useCallback(
    (files: File[]) => {
      if (viewModel.selection.modelId && !supportsVision(viewModel.selection.modelId)) {
        useToastStore.getState().addToast(
          'info',
          '当前模型可能不支持图片分析'
        )
      }
      try {
        addFiles(files)
      } catch (err) {
        const msg = err instanceof Error ? err.message : '图片添加失败'
        useToastStore.getState().addToast('error', msg)
      }
    },
    [viewModel.selection.modelId, addFiles]
  )

  /**
   * 发送消息：先上传图片附件，再发送文本 + attachmentIds，发送后清空附件。
   * 输入：message（用户输入文本）
   */
  const handleSend = useCallback(
    async (message: string) => {
      try {
        const attachmentIds = await uploadAll()
        await sendMessage(message, attachmentIds.length > 0 ? attachmentIds : undefined)
        clearAttachments()
      } catch (err) {
        const msg = err instanceof Error ? err.message : '发送失败'
        useToastStore.getState().addToast('error', msg)
      }
    },
    [sendMessage, uploadAll, clearAttachments]
  )

  // 代码面板左边缘拖拽调宽的 refs（记录拖拽起始状态，避免 closure 过期）
  const resizingRef = useRef(false)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)

  /**
   * 代码面板左边缘拖拽开始处理器：记录起始位置和宽度，注册 mousemove/mouseup 监听。
   * 手柄贴代码面板左边缘：鼠标左移（clientX 减小）→ delta 为负 → width 增大（符合直觉）。
   * 输入：e（React.MouseEvent）
   */
  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizingRef.current = true
    startXRef.current = e.clientX
    startWidthRef.current = codePanelWidth

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!resizingRef.current) return
      // 手柄贴代码面板左边缘，鼠标左移（clientX 减小）→ delta 为负 → width 增大（正确）
      const delta = moveEvent.clientX - startXRef.current
      setCodePanelWidth(startWidthRef.current - delta)
    }

    const onMouseUp = () => {
      resizingRef.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [codePanelWidth, setCodePanelWidth])

  return (
    <>
      <div className="flex h-full">
        {/* 对话区：常驻，flex-1 占满剩余宽度 */}
        <div className="flex h-full flex-col bg-surface-primary flex-1 min-w-0">
          <WorkspaceHeader {...viewModel.headerProps} />
          <WorkspaceTranscript
            {...viewModel.transcriptProps}
            oldestLoadedTurnId={oldestLoadedTurnId}
            runsById={runsById}
            isPlanMinimized={effectivePlanMinimized}
            onTogglePlanMinimize={() => setIsPlanMinimized((v) => !v)}
            onDetailClick={handleDetailClick}
            bottomInset={CHAT_INPUT_FALLBACK_INSET_PX}
          />

          {/* 输入区：与对话记录同宽（max-w-[1280px] mx-auto），不使用 overlay */}
          <div className="border-t border-edge bg-surface-primary">
             <div data-chat-input-frame className="mx-auto w-full max-w-[1280px] p-4">
              {plan && effectivePlanMinimized && (
                <PlanMinimizedBar
                  plan={plan}
                  onExpand={() => setIsPlanMinimized(false)}
                />
              )}
              <ChatInput
                onSend={handleSend}
                onCancel={cancelRun}
                agentMode={agentMode}
                onModeChange={(mode) => setMode(mode)}
                onImageAdd={handleImageAdd}
                attachments={attachments}
                onRemoveAttachment={removeAttachment}
                {...viewModel.inputProps}
              />
              {!viewModel.currentProject && (
                <p className="mt-2 text-sm text-content-muted">请先从左侧选择一个项目</p>
              )}
            </div>
          </div>
        </div>

        {/* 代码面板：固定宽度，收起时 width→0（CSS transition），不卸载 DOM（保留编辑器状态）
            inert 属性在收起时禁用键盘/鼠标交互，防止隐藏元素响应 Tab 键等操作 */}
        <div
          data-code-panel="true"
          className="flex h-full shrink-0 overflow-hidden border-l border-edge transition-[width] duration-200"
          style={{ width: codePanelOpen ? codePanelWidth : 0 }}
          {...(!codePanelOpen ? { inert: '' } : {})}
          aria-hidden={!codePanelOpen}
        >
          {/* 左边缘拖拽手柄（1px 宽，鼠标悬停显示 col-resize 光标） */}
          <div
            onMouseDown={handleResizeMouseDown}
            className="shrink-0 w-1 cursor-col-resize"
          />
          <div
            className={`flex h-full flex-col bg-surface-primary ${!codePanelOpen ? 'pointer-events-none' : ''}`}
            style={{ width: codePanelWidth }}
          >
            <div className="flex-1 min-h-0 overflow-hidden">
              <CodeTab />
            </div>
            <TerminalPanel />
          </div>
        </div>

        {/* 文件树侧边栏：仅在代码面板展开时渲染 */}
        {codePanelOpen && <FileSidebar />}
      </div>
    </>
  )
}
