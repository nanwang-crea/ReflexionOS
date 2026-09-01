/**
 * 文件功能：Agent 工作区主页面
 * 文件描述：左侧对话区（常驻，flex-1）+ 右侧代码面板（可折叠，宽度可拖拽调整）+
 *          文件树侧边栏（代码面板展开时显示）。整合对话运行时、消息发送、图片附件、
 *          终端面板、快捷键等多个子系统，是应用的核心工作界面
 * 核心逻辑：通过多个自定义 hook（useConversationRuntime/useConversationData/
 *          useCurrentSessionViewModel/useSendMessage/useImageUpload 等）拆分状态与业务逻辑，
 *          本组件主要负责聚合这些 hook 的输出并编排整体布局；
 *          键盘快捷键：Ctrl+` 切换终端、Ctrl+Shift+` 新建终端、Tab 切换 agent 模式（非输入框时）
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
 * 函数名：AgentWorkspace
 * 入参：无（默认导出的页面级组件，无 props）
 * 功能：渲染 Agent 工作区主页面，整合对话记录、消息输入、代码面板、终端面板、文件树等子系统
 * 运行逻辑：
 *   1. 从 workspace store 读取当前会话 id，驱动 useConversationRuntime（WebSocket 运行时：
 *      发起/取消对话、审批工具调用、切换模式等）和 useConversationData（消息列表/运行状态/计划）
 *   2. 通过 useSessionUnreadState 维持当前会话的已读基线，避免查看中的会话被计未读
 *   3. 从 conversation store 读取当前 Agent 模式（build/plan）和当前会话的 runsById
 *   4. 从 codeTab store 读取代码面板开关状态和宽度，从 terminal store 读取终端面板控制方法
 *   5. 注册全局键盘快捷键监听（Ctrl+`/Ctrl+Shift+`/Tab），并让代码面板开关与文件树侧边栏联动
 *   6. 通过 useCurrentSessionViewModel 聚合出头部/对话记录/输入框所需的视图模型属性
 *   7. 通过 useSendMessage、useImageUpload 组装发送消息与图片附件上传的能力
 *   8. 渲染整体三段式布局：左侧对话区（常驻）+ 代码面板（可拖拽调宽、可折叠但不卸载 DOM）+
 *      文件树侧边栏（仅代码面板展开时渲染）
 * 出参：JSX.Element - 工作区主页面的完整 DOM 结构，包含 Header、对话记录、输入框、代码面板和文件树
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
   * 函数名：toggleMode
   * 入参：无（依赖闭包中的 currentSessionId、agentMode、isRunning）
   * 功能：在 build 模式和 plan 模式之间切换 Agent 工作模式
   * 运行逻辑：若无当前会话或对话正在运行，直接忽略；否则取反当前模式并调用 setMode 更新
   * 出参：无（副作用型回调，通过 setMode 触发状态更新）
   */
  const toggleMode = useCallback(() => {
    if (!currentSessionId || isRunning) return
    const newMode: AgentMode = agentMode === 'build' ? 'plan' : 'build'
    setMode(newMode)
  }, [currentSessionId, agentMode, isRunning, setMode])

  /**
   * 函数名：handleReset
   * 入参：无（依赖闭包中的 currentSessionId）
   * 功能：清空当前会话的全部对话记录（破坏性操作）
   * 运行逻辑：
   *   1. 若无当前会话直接返回
   *   2. 弹出二次确认对话框（danger 样式），用户取消则不执行任何操作
   *   3. 确认后调用 resetConversationRuntime 执行重置（先停止运行中的对话，再清空记录，不可恢复）
   * 出参：Promise<void>（异步回调，无返回值，通过副作用清空对话状态）
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

  /**
   * 函数名：useEffect（注册全局键盘快捷键）
   * 入参：依赖 [togglePanel, createTerminal, currentProject, toggleMode]
   * 功能：监听全局键盘事件，实现终端面板切换、新建终端、Tab 切换 Agent 模式等快捷键
   * 运行逻辑：
   *   1. 定义 handleKeyDown：Ctrl+` 切换终端面板；Ctrl+Shift+` 以当前项目路径新建终端；
   *      Tab（且未按 Ctrl/Shift/Meta）在焦点不在输入框（textarea/input）时切换 Agent 模式
   *   2. 挂载时在 window 上注册 keydown 监听，卸载或依赖变化时移除监听
   * 出参：无（副作用型 hook）
   */
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

  /**
   * 函数名：useEffect（代码面板与文件树联动）
   * 入参：依赖 [codePanelOpen, setSidebarOpen]
   * 功能：保持代码面板开关状态与文件树侧边栏开关状态同步
   * 运行逻辑：codePanelOpen 变化时，将其值同步写入 codeTab store 的 sidebarOpen
   *          （关闭代码面板时同步关闭文件树，展开时同步展开）
   * 出参：无（副作用型 hook）
   */
  useEffect(() => {
    setSidebarOpen(codePanelOpen)
  }, [codePanelOpen, setSidebarOpen])

  /**
   * 函数名：handleDetailClick
   * 入参：
   *   - detail (ActionReceiptDetail): 执行详情对象，包含 arguments（工具调用参数）和 category（操作类别）
   * 功能：点击对话记录中的执行详情时，在代码面板中自动打开对应文件
   * 运行逻辑：
   *   1. 从 detail.arguments 中取出 path 字段，若不存在或非法则直接返回不处理
   *   2. 根据 detail.category 是否属于 edit/create/delete 决定用 diff 视图还是普通 edit 视图
   *   3. 调用 openFile 在代码面板打开该文件并切换到对应视图模式
   * 出参：无（副作用型回调，通过 openFile 触发代码面板状态更新）
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
   * 函数名：handleImageAdd
   * 入参：
   *   - files (File[]): 用户选择/拖拽添加的图片文件数组
   * 功能：将图片文件加入待发送附件列表，并在当前模型可能不支持视觉时给出提示
   * 运行逻辑：
   *   1. 若当前选中模型存在且 supportsVision 判断其不支持视觉，弹出 info 级提示 toast（不阻断操作）
   *   2. 调用 addFiles 将文件加入附件状态；若添加过程抛出异常，捕获后弹出 error 级 toast
   * 出参：无（副作用型回调，通过 addFiles 更新附件状态或提示错误）
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
   * 函数名：handleSend
   * 入参：
   *   - message (string): 用户在输入框中输入的文本内容
   * 功能：发送一条消息，若有待发送的图片附件则先上传附件再一并发送
   * 运行逻辑：
   *   1. 调用 uploadAll 上传所有待发送的图片附件，得到已上传附件的 id 列表
   *   2. 调用 sendMessage 发送文本消息，若附件 id 列表非空则一并携带
   *   3. 发送后调用 clearAttachments 清空本地附件状态
   *   4. 上传或发送过程中任何异常都会被捕获，转换为 error 级提示 toast
   * 出参：Promise<void>（异步回调，无返回值，通过副作用发送消息、更新附件状态或提示错误）
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
   * 函数名：handleResizeMouseDown
   * 入参：
   *   - e (React.MouseEvent): 鼠标在代码面板左边缘拖拽手柄上按下时触发的事件对象
   * 功能：处理代码面板宽度拖拽调整的起始逻辑，并在拖拽过程中实时更新面板宽度
   * 运行逻辑：
   *   1. 阻止默认行为，标记 resizingRef 为 true，记录起始鼠标横坐标和起始面板宽度（存入 ref，
   *      避免闭包捕获过期的 state）
   *   2. 定义 onMouseMove：仅在 resizingRef 为 true 时响应；手柄贴代码面板左边缘，
   *      鼠标左移（clientX 减小）对应 delta 为负，此时应让宽度增大，因此新宽度 = 起始宽度 - delta
   *   3. 定义 onMouseUp：结束拖拽状态，移除 mousemove/mouseup 监听，恢复鼠标样式和文本选中行为
   *   4. 在 document 上注册 mousemove/mouseup 监听，并将鼠标样式设为 col-resize、禁用文本选中
   * 出参：无（副作用型回调，通过 setCodePanelWidth 实时更新代码面板宽度）
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
