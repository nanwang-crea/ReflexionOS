/**
 * 文件功能：代码编辑区标签栏
 * 文件描述：展示已打开文件的标签列表（含脏标记与关闭按钮），以及编辑/Diff 视图切换按钮
 * 核心逻辑：纯展示 + 交互转发组件，所有状态变更均通过 props 回调转发给上层 CodeTab 处理
 */
import { X, FileCode, GitCompare } from 'lucide-react'
import type { OpenFile, ViewMode } from '@/features/code/stores/codeTab.store'

interface CodeTabBarProps {
  openFiles: OpenFile[]
  activeFileId: string | null
  viewMode: ViewMode
  onSelectFile: (id: string) => void
  onCloseFile: (id: string) => void
  onToggleViewMode: () => void
}

/**
 * 组件名：CodeTabBar
 * 入参（props，CodeTabBarProps）：
 *   - openFiles (OpenFile[]): 已打开的文件列表
 *   - activeFileId (string | null): 当前激活的文件 ID
 *   - viewMode (ViewMode): 当前视图模式（edit/diff），决定切换按钮的文案与图标
 *   - onSelectFile ((id) => void): 点击标签切换激活文件
 *   - onCloseFile ((id) => void): 点击标签关闭按钮关闭文件
 *   - onToggleViewMode (() => void): 点击右侧按钮切换编辑/Diff 视图
 * 作用/渲染逻辑：
 *   1. 若无打开文件则不渲染任何内容
 *   2. 遍历 openFiles 渲染可横向滚动的标签列表，脏文件显示圆点标记，标签内含独立的关闭按钮
 *   3. 右侧渲染视图切换按钮，按 viewMode 展示不同图标/文案
 * 返回值：JSX.Element | null - 标签栏，或无打开文件时为 null
 */
export function CodeTabBar({
  openFiles,
  activeFileId,
  viewMode,
  onSelectFile,
  onCloseFile,
  onToggleViewMode,
}: CodeTabBarProps) {
  if (openFiles.length === 0) return null

  return (
    <div className="flex items-center border-b border-edge bg-surface-primary">
      <div className="flex flex-1 overflow-x-auto">
        {openFiles.map((file) => {
          const isActive = file.id === activeFileId
          const filename = file.path.split('/').pop() ?? file.path
          return (
            <button
              key={file.id}
              type="button"
              onClick={() => onSelectFile(file.id)}
              className={`group relative flex shrink-0 items-center gap-1.5 border-r border-edge px-3 py-1.5 text-sm transition-colors ${
                isActive
                  ? 'bg-surface-secondary text-content-primary'
                  : 'bg-surface-primary text-content-secondary hover:bg-surface-tertiary'
              }`}
            >
              {file.isDirty && <span className="text-status-warning text-xs">●</span>}
              <span className="truncate max-w-[120px]">{filename}</span>
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation()
                  onCloseFile(file.id)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.stopPropagation()
                    onCloseFile(file.id)
                  }
                }}
                className="ml-1 rounded p-0.5 opacity-0 group-hover:opacity-100 hover:bg-surface-tertiary hover:text-content-primary"
              >
                <X className="h-3 w-3" />
              </span>
            </button>
          )
        })}
      </div>
      <button
        type="button"
        onClick={onToggleViewMode}
        className="flex shrink-0 items-center gap-1.5 border-l border-edge px-3 py-1.5 text-sm text-content-secondary transition-colors hover:bg-surface-tertiary hover:text-content-primary"
        title={viewMode === 'edit' ? '切换到 Diff 视图' : '切换到编辑视图'}
      >
        {viewMode === 'edit' ? (
          <>
            <GitCompare className="h-3.5 w-3.5" />
            <span>Diff</span>
          </>
        ) : (
          <>
            <FileCode className="h-3.5 w-3.5" />
            <span>编辑</span>
          </>
        )}
      </button>
    </div>
  )
}
