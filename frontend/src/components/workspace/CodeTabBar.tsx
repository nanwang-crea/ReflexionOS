import { X, FileCode, GitCompare } from 'lucide-react'
import type { OpenFile, ViewMode } from '@/features/code/codeTabStore'

interface CodeTabBarProps {
  openFiles: OpenFile[]
  activeFileId: string | null
  viewMode: ViewMode
  onSelectFile: (id: string) => void
  onCloseFile: (id: string) => void
  onToggleViewMode: () => void
}

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
