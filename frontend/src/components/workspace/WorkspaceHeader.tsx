import { FolderTree, TerminalSquare } from 'lucide-react'
import type { ConnectionStatus } from '@/features/workspace/types'
import { useCodeTabStore, type WorkspaceTab } from '@/features/code/stores/codeTab.store'
import { useTerminalStore } from '@/features/terminal/stores/terminal.store'

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
  const sidebarOpen = useCodeTabStore((s) => s.sidebarOpen)
  const toggleSidebar = useCodeTabStore((s) => s.toggleSidebar)
  const panelVisible = useTerminalStore((s) => s.panelVisible)
  const togglePanel = useTerminalStore((s) => s.togglePanel)

  return (
    <div className="flex flex-col gap-3 border-b border-edge bg-surface-primary px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        {workspaceTab === 'code' && (
          <button
            type="button"
            onClick={toggleSidebar}
            className={`rounded-md p-1.5 transition-colors ${
              sidebarOpen
                ? 'text-content-primary bg-surface-tertiary'
                : 'text-content-muted hover:bg-surface-tertiary hover:text-content-secondary'
            }`}
            title={sidebarOpen ? '收起文件栏' : '展开文件栏'}
          >
            <FolderTree className="h-4 w-4" />
          </button>
        )}
        {workspaceTab === 'code' && (
          <button
            type="button"
            onClick={togglePanel}
            className={`rounded-md p-1.5 transition-colors ${
              panelVisible
                ? 'text-content-primary bg-surface-tertiary'
                : 'text-content-muted hover:bg-surface-tertiary hover:text-content-secondary'
            }`}
            title={panelVisible ? '隐藏终端' : '显示终端'}
          >
            <TerminalSquare className="h-4 w-4" />
          </button>
        )}
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold text-content-primary">{title}</h2>
          {projectPath && (
            <p className="truncate text-sm text-content-muted">{projectPath}</p>
          )}
        </div>
      </div>
        <div className="flex w-full items-center justify-center gap-1 rounded-lg bg-surface-tertiary p-1 sm:w-auto">
          {(['chat', 'code'] as WorkspaceTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setWorkspaceTab(tab)}
              className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                workspaceTab === tab
                  ? 'bg-surface-primary text-content-primary shadow-sm'
                  : 'text-content-muted hover:text-content-secondary'
              }`}
            >
              {tab === 'chat' ? '对话' : '代码'}
            </button>
          ))}
        </div>
      <div className="flex w-full flex-wrap items-center justify-between gap-3 sm:justify-end lg:w-auto">
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${
            connectionStatus === 'connected' ? 'bg-status-success' :
            connectionStatus === 'connecting' ? 'bg-status-warning' : 'bg-content-muted'
          }`} />
          <span className="text-sm text-content-muted">
            {connectionStatus === 'connected' ? '已连接' :
             connectionStatus === 'connecting' ? '连接中...' : '未连接'}
          </span>
        </div>
        <button
          onClick={onReset}
          className="rounded-lg px-3 py-1.5 text-sm text-content-secondary hover:bg-surface-tertiary"
        >
          重置对话
        </button>
      </div>
    </div>
  )
}
