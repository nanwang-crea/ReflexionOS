import type { ConnectionStatus } from '@/features/workspace/types'
import { useCodeTabStore, type WorkspaceTab } from '@/features/code/codeTabStore'

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
  const workspaceTab = useCodeTabStore((s) => s.workspaceTab)
  const setWorkspaceTab = useCodeTabStore((s) => s.setWorkspaceTab)

  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        {projectPath && (
          <p className="text-sm text-gray-500">{projectPath}</p>
        )}
      </div>
        <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1">
          {(['chat', 'code'] as WorkspaceTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setWorkspaceTab(tab)}
              className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                workspaceTab === tab
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab === 'chat' ? '对话' : '代码'}
            </button>
          ))}
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
