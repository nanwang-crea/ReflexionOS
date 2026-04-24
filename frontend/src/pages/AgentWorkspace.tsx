import { ChatInput } from '@/components/chat/ChatInput'
import { WorkspaceHeader } from '@/components/workspace/WorkspaceHeader'
import { WorkspaceTranscript } from '@/components/workspace/WorkspaceTranscript'
import { useConversationData } from '@/hooks/useConversationData'
import { useConversationRuntime } from '@/hooks/useConversationRuntime'
import { useCurrentSessionViewModel } from '@/hooks/useCurrentSessionViewModel'
import { useSendMessage } from '@/hooks/useSendMessage'
import { useWorkspaceStore } from '@/stores/workspaceStore'

export default function AgentWorkspace() {
  const currentSessionId = useWorkspaceStore((state) => state.currentSessionId)
  const {
    connectionStatus,
    isCancelling,
    startTurn,
    cancelRun,
    resetConversationRuntime,
  } = useConversationRuntime(currentSessionId)
  const { messages, isRunning } = useConversationData(currentSessionId)
  const viewModel = useCurrentSessionViewModel({
    messages,
    isRunning,
    isCancelling,
    connectionStatus,
    onReset: resetConversationRuntime,
  })
  const { sendMessage } = useSendMessage({
    currentSession: viewModel.currentSession,
    configured: viewModel.configured,
    selection: viewModel.selection,
    startTurn,
  })

  return (
    <div className="flex h-full flex-col bg-white">
      <WorkspaceHeader {...viewModel.headerProps} />

      <WorkspaceTranscript {...viewModel.transcriptProps} />

      <div className="border-t border-gray-200 bg-white p-4">
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
  )
}
