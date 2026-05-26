import { ChevronDown, ChevronRight, Plus, Minus, RotateCcw } from 'lucide-react'
import type { GitFileChange, GitStatusCode } from '@/types/git'
import { GitFileItem } from './GitFileItem'
import { useGitStore } from '@/features/git/gitStore'

interface GitFileGroupProps {
  title: string
  files: GitFileChange[]
  section: 'staged' | 'unstaged' | 'untracked'
  collapsed: boolean
  onToggleCollapsed: () => void
}

export function GitFileGroup({ title, files, section, collapsed, onToggleCollapsed }: GitFileGroupProps) {
  const stageAll = useGitStore((s) => s.stageAll)
  const unstageAll = useGitStore((s) => s.unstageAll)
  const discardAll = useGitStore((s) => s.discardAll)

  if (files.length === 0) return null

  return (
    <div className="border-b border-edge-subtle">
      <div className="flex items-center px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-surface-tertiary">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="flex items-center gap-1.5 flex-1 min-w-0"
        >
          {collapsed ? (
            <ChevronRight className="h-3 w-3 shrink-0 text-content-muted" />
          ) : (
            <ChevronDown className="h-3 w-3 shrink-0 text-content-muted" />
          )}
          <span className="truncate">{title}</span>
          <span className="shrink-0 text-content-muted">({files.length})</span>
        </button>

        <div className="flex shrink-0 items-center gap-0.5 ml-1">
          {section === 'staged' && (
            <button
              type="button"
              onClick={() => unstageAll()}
              className="rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
              title="Unstage All"
            >
              <Minus className="h-3 w-3" />
            </button>
          )}
          {section === 'unstaged' && (
            <>
              <button
                type="button"
                onClick={() => stageAll()}
                className="rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
                title="Stage All"
              >
                <Plus className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => discardAll()}
                className="rounded p-0.5 text-content-muted hover:text-status-error hover:bg-surface-tertiary"
                title="Discard All"
              >
                <RotateCcw className="h-3 w-3" />
              </button>
            </>
          )}
          {section === 'untracked' && (
            <>
              <button
                type="button"
                onClick={() => stageAll()}
                className="rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
                title="Stage All"
              >
                <Plus className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => discardAll()}
                className="rounded p-0.5 text-content-muted hover:text-status-error hover:bg-surface-tertiary"
                title="Discard All"
              >
                <RotateCcw className="h-3 w-3" />
              </button>
            </>
          )}
        </div>
      </div>
      {!collapsed && (
        <div className="pb-1">
          {files.map((file) => (
            <GitFileItem
              key={file.path}
              path={file.path}
              status={file.status as GitStatusCode}
              insertions={file.insertions}
              deletions={file.deletions}
              section={section}
            />
          ))}
        </div>
      )}
    </div>
  )
}
