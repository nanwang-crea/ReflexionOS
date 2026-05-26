import { File, Plus, Minus, RotateCcw } from 'lucide-react'
import type { GitStatusCode } from '@/types/git'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { useGitStore } from '@/features/git/gitStore'
import { useToast } from '@/hooks/useToast'

const GIT_STATUS_STYLES: Record<GitStatusCode, string> = {
  M: 'text-status-success',
  A: 'text-status-success',
  D: 'text-status-error',
  U: 'text-content-muted',
  R: 'text-accent',
}

interface GitFileItemProps {
  path: string
  status: GitStatusCode
  insertions?: number | null
  deletions?: number | null
  section: 'staged' | 'unstaged' | 'untracked'
}

export function GitFileItem({ path, status, insertions, deletions, section }: GitFileItemProps) {
  const setActiveFile = useCodeTabStore((s) => s.setActiveFile)
  const stageFiles = useGitStore((s) => s.stageFiles)
  const unstageFiles = useGitStore((s) => s.unstageFiles)
  const discardChanges = useGitStore((s) => s.discardChanges)
  const addToast = useToast()

  const filename = path.split('/').pop() ?? path

  const handleOpenFile = () => {
    setActiveFile(path, '')
  }

  const handleStage = () => {
    stageFiles([path])
  }

  const handleUnstage = () => {
    unstageFiles([path])
  }

  const handleDiscard = async () => {
    discardChanges([path])
    addToast('已丢弃变更: ' + filename, 'info')
  }

  return (
    <div className="group flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-surface-tertiary">
      <File className="h-3.5 w-3.5 shrink-0 text-content-muted" />
      <button
        type="button"
        onClick={handleOpenFile}
        className="flex-1 truncate text-left text-sm text-content-secondary hover:text-content-primary"
        title={path}
      >
        {filename}
      </button>
      {(insertions != null || deletions != null) && (
        <span className="text-xs text-content-muted">
          {insertions != null && <span className="text-status-success">+{insertions}</span>}
          {deletions != null && <span className="text-status-error">-{deletions}</span>}
        </span>
      )}
      <span className={`text-xs font-mono ${GIT_STATUS_STYLES[status]}`}>{status}</span>
      {section === 'staged' && (
        <button
          type="button"
          onClick={handleUnstage}
          className="rounded p-0.5 text-content-muted opacity-0 group-hover:opacity-100 hover:text-content-primary hover:bg-surface-tertiary"
          title="Unstage"
        >
          <Minus className="h-3 w-3" />
        </button>
      )}
      {(section === 'unstaged' || section === 'untracked') && (
        <>
          <button
            type="button"
            onClick={handleStage}
            className="rounded p-0.5 text-content-muted opacity-0 group-hover:opacity-100 hover:text-content-primary hover:bg-surface-tertiary"
            title="Stage"
          >
            <Plus className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={handleDiscard}
            className="rounded p-0.5 text-content-muted opacity-0 group-hover:opacity-100 hover:text-status-error hover:bg-surface-tertiary"
            title="丢弃变更"
          >
            <RotateCcw className="h-3 w-3" />
          </button>
        </>
      )}
    </div>
  )
}
