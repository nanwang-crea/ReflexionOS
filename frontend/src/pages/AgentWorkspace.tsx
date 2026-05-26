import { useCallback, useEffect, useState } from 'react'
import { ChatInput } from '@/components/chat/ChatInput'
import { CodeTab } from '@/components/workspace/CodeTab'
import { PlanMinimizedBar } from '@/components/workspace/PlanProgress'
import { WorkspaceHeader } from '@/components/workspace/WorkspaceHeader'
import { WorkspaceTranscript } from '@/components/workspace/WorkspaceTranscript'
import { TerminalPanel } from '@/components/terminal/TerminalPanel'
import { useConversationStore } from '@/features/conversation/conversationStore'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { useTerminalStore } from '@/features/terminal/terminalStore'
import { useConversationData } from '@/hooks/useConversationData'
import { useConversationRuntime } from '@/hooks/useConversationRuntime'
import { useCurrentSessionViewModel } from '@/hooks/useCurrentSessionViewModel'
import { useSendMessage } from '@/hooks/useSendMessage'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useProjectStore } from '@/stores/projectStore'
import { ToastContainer } from '@/components/common/Toast'
import { FileSidebar } from '@/components/workspace/FileSidebar'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'

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
    resetConversationRuntime,
  } = useConversationRuntime(currentSessionId)
  const { messages, isRunning, plan } = useConversationData(currentSessionId)
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
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [togglePanel, createTerminal, currentProject])

  useEffect(() => {
    if (workspaceTab === 'code') {
      setSidebarOpen(true)
    } else {
      setSidebarOpen(false)
    }
  }, [workspaceTab, setSidebarOpen])

  const handleDetailClick = useCallback((detail: ActionReceiptDetail) => {
    const path = detail.arguments?.path as string | undefined
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
    onReset: resetConversationRuntime,
    onApprovalAction: (action, payload) => {
      if (action === 'approve') {
        approveTool(payload.runId, payload.approvalId)
        return
      }

      denyTool(payload.runId, payload.approvalId)
    },
  })
  const { sendMessage } = useSendMessage({
    currentSession: viewModel.currentSession,
    configured: viewModel.configured,
    selection: viewModel.selection,
    startTurn,
  })

  return (
    <>
      <ToastContainer />
      <div className="flex h-full">
        <div className="flex h-full flex-col bg-surface-primary flex-1 min-w-0">
          <WorkspaceHeader {...viewModel.headerProps} />

        {workspaceTab === 'code' ? (
          <>
            <div className="flex-1 min-h-0 overflow-hidden">
              <CodeTab />
            </div>
            <TerminalPanel />
          </>
        ) : (
          <>
            <WorkspaceTranscript
              {...viewModel.transcriptProps}
              runsById={runsById}
              isPlanMinimized={effectivePlanMinimized}
              onTogglePlanMinimize={() => setIsPlanMinimized((v) => !v)}
              onDetailClick={handleDetailClick}
            />

            <div className="border-t border-edge bg-surface-primary">
              {plan && effectivePlanMinimized && (
                <PlanMinimizedBar
                  plan={plan}
                  onExpand={() => setIsPlanMinimized(false)}
                />
              )}
              <div className="p-4">
                <ChatInput
                  onSend={sendMessage}
                  onCancel={cancelRun}
                  {...viewModel.inputProps}
                />
                {!viewModel.currentProject && (
                  <p className="mt-2 text-sm text-content-muted">请先从左侧选择一个项目</p>
                )}
              </div>
            </div>
          </>
        )}
        </div>
        {workspaceTab === 'code' && <FileSidebar />}
      </div>
    </>
  )
}
