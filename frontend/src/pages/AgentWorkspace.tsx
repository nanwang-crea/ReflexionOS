import { ChatInput } from '@/components/chat/ChatInput'
import { WorkspaceHeader } from '@/components/workspace/WorkspaceHeader'
import { WorkspaceTranscript } from '@/components/workspace/WorkspaceTranscript'
import { useCurrentSessionViewModel } from '@/hooks/useCurrentSessionViewModel'
import { useExecutionRuntime } from '@/hooks/useExecutionRuntime'
import { useSendMessage } from '@/hooks/useSendMessage'
import { useWorkspaceStore } from '@/stores/workspaceStore'

export default function AgentWorkspace() {
  const currentSessionId = useWorkspaceStore((state) => state.currentSessionId)
  const {
    overlayItems,
    activeRoundItems,
    connectionStatus,
    startExecutionRun,
    handleCancel,
    resetExecutionRuntime,
  } = useExecutionRuntime(currentSessionId)
  const viewModel = useCurrentSessionViewModel({
    overlayItems,
    activeRoundItems,
    connectionStatus,
    onReset: resetExecutionRuntime,
  })
  const { sendMessage } = useSendMessage({
    currentSession: viewModel.currentSession,
    configured: viewModel.configured,
    selection: viewModel.selection,
    startExecutionRun,
  })

  return (
    <div className="flex h-full flex-col bg-white">
      <WorkspaceHeader {...viewModel.headerProps} />

      <WorkspaceTranscript {...viewModel.transcriptProps} />

      <div className="border-t border-gray-200 bg-white p-4">
        <ChatInput
          onSend={sendMessage}
          onCancel={handleCancel}
          {...viewModel.inputProps}
        />
        {!viewModel.currentProject && (
          <p className="mt-2 text-sm text-gray-500">请先从左侧选择一个项目</p>
        )}
      </div>
    </div>
  )
}
