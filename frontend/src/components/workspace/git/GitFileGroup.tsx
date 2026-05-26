import { ChevronDown, ChevronRight } from 'lucide-react'
import type { GitFileChange, GitStatusCode } from '@/types/git'
import { GitFileItem } from './GitFileItem'

interface GitFileGroupProps {
  title: string
  files: GitFileChange[]
  section: 'staged' | 'unstaged' | 'untracked'
  collapsed: boolean
  onToggleCollapsed: () => void
}

export function GitFileGroup({ title, files, section, collapsed, onToggleCollapsed }: GitFileGroupProps) {
  if (files.length === 0) return null

  return (
    <div className="border-b border-edge-subtle">
      <button
        type="button"
        onClick={onToggleCollapsed}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-surface-tertiary"
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3 shrink-0 text-content-muted" />
        ) : (
          <ChevronDown className="h-3 w-3 shrink-0 text-content-muted" />
        )}
        <span>{title}</span>
        <span className="ml-1 text-content-muted">({files.length})</span>
      </button>
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
