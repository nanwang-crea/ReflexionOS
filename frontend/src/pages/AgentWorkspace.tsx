import { useCallback, useState } from 'react'
import { ChatInput } from '@/components/chat/ChatInput'
import { CodeTab } from '@/components/workspace/CodeTab'
import { PlanMinimizedBar } from '@/components/workspace/PlanProgress'
import { WorkspaceHeader } from '@/components/workspace/WorkspaceHeader'
import { WorkspaceTranscript } from '@/components/workspace/WorkspaceTranscript'
import { useConversationStore } from '@/features/conversation/conversationStore'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { useConversationData } from '@/hooks/useConversationData'
import { useConversationRuntime } from '@/hooks/useConversationRuntime'
import { useCurrentSessionViewModel } from '@/hooks/useCurrentSessionViewModel'
import { useSendMessage } from '@/hooks/useSendMessage'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { ToastContainer } from '@/components/common/Toast'
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
  const setActiveFile = useCodeTabStore((s) => s.setActiveFile)

  const handleDetailClick = useCallback((detail: ActionReceiptDetail) => {
    const path = detail.arguments?.path as string | undefined
    if (!path) return
    setActiveFile(path, '')
  }, [setActiveFile])

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
      <div className="flex h-full flex-col bg-white">
        <WorkspaceHeader {...viewModel.headerProps} />

        {workspaceTab === 'code' ? (
          <CodeTab />
        ) : (
          <>
            <WorkspaceTranscript
              {...viewModel.transcriptProps}
              runsById={runsById}
              isPlanMinimized={effectivePlanMinimized}
              onTogglePlanMinimize={() => setIsPlanMinimized((v) => !v)}
              onDetailClick={handleDetailClick}
            />

            <div className="border-t border-gray-200 bg-white">
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
                  <p className="mt-2 text-sm text-gray-500">请先从左侧选择一个项目</p>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
