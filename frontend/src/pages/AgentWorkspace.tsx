import { useCallback, useEffect, useState } from 'react'
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

const CHAT_INPUT_FALLBACK_INSET_PX = 80

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
  const workspaceTab = useCodeTabStore((s) => s.workspaceTab)
  const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)
  const openFile = useCodeTabStore((s) => s.openFile)
  const togglePanel = useTerminalStore((s) => s.togglePanel)
  const createTerminal = useTerminalStore((s) => s.createTerminal)
  const currentProject = useProjectStore((s) => s.currentProject)

  const toggleMode = useCallback(() => {
    if (!currentSessionId || isRunning) return
    const newMode: AgentMode = agentMode === 'build' ? 'plan' : 'build'
    setMode(newMode)
  }, [currentSessionId, agentMode, isRunning, setMode])

  // 重置对话是破坏性操作，先二次确认再执行（先停后清，不可恢复）。
  const handleReset = useCallback(async () => {
    if (!currentSessionId) return
    const confirmed = await nativeDialogService.confirmAction(
      '确定要清空当前会话的全部对话记录吗？此操作不可恢复。',
      { variant: 'danger' }
    )
    if (!confirmed) return
    void resetConversationRuntime()
  }, [currentSessionId, resetConversationRuntime])

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

  useEffect(() => {
    if (workspaceTab === 'code') {
      setSidebarOpen(true)
    } else {
      setSidebarOpen(false)
    }
  }, [workspaceTab, setSidebarOpen])

  // ChatInputFrame is a flex sibling (not overlay), so no dynamic inset needed

  const handleDetailClick = useCallback((detail: ActionReceiptDetail) => {
    const args = detail.arguments
    if (!args || typeof args !== 'object') return
    const path = typeof args.path === 'string' ? args.path : undefined
    if (!path) return
    const viewMode = ['edit', 'create', 'delete'].includes(detail.category) ? 'diff' : 'edit'
    openFile(path, viewMode)
  }, [openFile])

  // When plan disappears (run ends), reset minimized state so next plan starts expanded
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

  return (
    <>
      <div className="flex h-full">
        <div className={`flex h-full flex-col bg-surface-primary flex-1 min-w-0 ${workspaceTab === 'code' ? '' : 'hidden'}`}>
          <WorkspaceHeader {...viewModel.headerProps} />
          <div className="flex-1 min-h-0 overflow-hidden">
            <CodeTab />
          </div>
          <TerminalPanel />
        </div>

        <div className={`flex h-full flex-col bg-surface-primary flex-1 min-w-0 ${workspaceTab === 'chat' ? '' : 'hidden'}`}>
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
        {workspaceTab === 'code' && <FileSidebar />}
      </div>
    </>
  )
}
