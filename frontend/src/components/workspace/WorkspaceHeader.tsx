/**
 * 工作区顶部 Header 组件：显示项目标题、WebSocket 连接状态，
 * 并提供文件树开关、终端开关、重置对话和代码面板折叠/展开按钮。
 */

import { FolderTree, PanelRightClose, PanelRightOpen, TerminalSquare } from 'lucide-react'
import type { ConnectionStatus } from '@/features/workspace/types'
import { useCodeTabStore } from '@/features/code/stores/codeTab.store'
import { useTerminalStore } from '@/features/terminal/stores/terminal.store'

interface WorkspaceHeaderProps {
  title: string
  projectPath?: string | null
  connectionStatus: ConnectionStatus
  onReset: () => void | Promise<void>
}

/**
 * WorkspaceHeader 组件。
 * 输入：title（项目名）、projectPath（项目路径，可选）、
 *       connectionStatus（connected/connecting/disconnected）、onReset（重置对话回调）
 * 输出：JSX，包含左侧标题区和右侧操作区
 * 布局：小屏垂直排列，lg 断点起水平排列（flex-row）
 */
export function WorkspaceHeader({
  title,
  projectPath,
  connectionStatus,
  onReset,
}: WorkspaceHeaderProps) {
  const codePanelOpen = useCodeTabStore((s) => s.codePanelOpen)
  const toggleCodePanel = useCodeTabStore((s) => s.toggleCodePanel)
  const sidebarOpen = useCodeTabStore((s) => s.sidebarOpen)
  const toggleSidebar = useCodeTabStore((s) => s.toggleSidebar)
  const panelVisible = useTerminalStore((s) => s.panelVisible)
  const togglePanel = useTerminalStore((s) => s.togglePanel)

  return (
    <div className="flex flex-col gap-3 border-b border-edge bg-surface-primary px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
      {/* 左侧：文件树/终端快捷开关 + 项目标题 */}
      <div className="flex min-w-0 items-center gap-3">
        {/* 代码面板打开时才显示文件树和终端开关，避免无意义的占位 */}
        {codePanelOpen && (
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
        {codePanelOpen && (
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

      {/* 右侧：连接状态指示 + 重置对话 + 代码面板折叠开关 */}
      <div className="flex w-full flex-wrap items-center justify-between gap-3 sm:justify-end lg:w-auto">
        {/* 连接状态：绿色/黄色/灰色圆点 + 文字 */}
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
        <div className="flex items-center gap-1">
          <button
            onClick={onReset}
            className="rounded-lg px-3 py-1.5 text-sm text-content-secondary hover:bg-surface-tertiary"
          >
            重置对话
          </button>
          {/* 代码面板折叠开关，固定在 Header 最右侧 */}
          <button
            type="button"
            onClick={toggleCodePanel}
            className={`rounded-md p-1.5 transition-colors ${
              codePanelOpen
                ? 'text-content-primary bg-surface-tertiary'
                : 'text-content-muted hover:bg-surface-tertiary hover:text-content-secondary'
            }`}
            title={codePanelOpen ? '收起代码面板' : '展开代码面板'}
          >
            {codePanelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}
