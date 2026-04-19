import type { ConnectionStatus } from '@/features/workspace/types'

interface WorkspaceHeaderProps {
  title: string
  projectPath?: string | null
  connectionStatus: ConnectionStatus
  onReset: () => void
}

export function WorkspaceHeader({
  title,
  projectPath,
  connectionStatus,
  onReset,
}: WorkspaceHeaderProps) {
  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        {projectPath && (
          <p className="text-sm text-gray-500">{projectPath}</p>
        )}
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${
            connectionStatus === 'connected' ? 'bg-green-500' :
            connectionStatus === 'connecting' ? 'bg-yellow-500' : 'bg-gray-300'
          }`} />
          <span className="text-sm text-gray-500">
            {connectionStatus === 'connected' ? '已连接' :
             connectionStatus === 'connecting' ? '连接中...' : '未连接'}
          </span>
        </div>
        <button
          onClick={onReset}
          className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
        >
          重置对话
        </button>
      </div>
    </div>
  )
}
