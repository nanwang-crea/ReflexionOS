import { Check, RotateCcw } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'
import { useState } from 'react'

export function GitCommitInput() {
  const commitMessage = useGitStore((s) => s.commitMessage)
  const setCommitMessage = useGitStore((s) => s.setCommitMessage)
  const commit = useGitStore((s) => s.commit)
  const stagedFiles = useGitStore((s) => s.stagedFiles)
  const isCommitting = useGitStore((s) => s.isCommitting)

  const [amend, setAmend] = useState(false)
  const canCommit = (stagedFiles.length > 0 || amend) && commitMessage.trim().length > 0 && !isCommitting

  const handleCommit = () => {
    if (!canCommit) return
    commit(commitMessage.trim(), amend)
    if (amend) setAmend(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && canCommit) {
      e.preventDefault()
      handleCommit()
    }
  }

  return (
    <div className="border-b border-edge-subtle px-3 py-2">
      <textarea
        value={commitMessage}
        onChange={(e) => setCommitMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={amend ? "Amend commit message..." : "Commit message..."}
        rows={2}
        className="w-full resize-none rounded-md border border-edge-subtle bg-surface-primary px-2 py-1.5 text-sm text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none"
      />
      <div className="mt-1.5 flex items-center gap-1.5">
        <button
          type="button"
          onClick={handleCommit}
          disabled={!canCommit}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            canCommit
              ? 'bg-accent text-white hover:bg-accent-hover'
              : 'bg-surface-tertiary text-content-muted cursor-not-allowed'
          }`}
        >
          <Check className="h-3.5 w-3.5" />
          {isCommitting ? '...' : amend ? 'Amend' : 'Commit'}
        </button>
        <button
          type="button"
          onClick={() => setAmend(!amend)}
          title="Amend 上一次提交"
          className={`shrink-0 flex items-center gap-1 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors ${
            amend
              ? 'border-status-warning-border bg-status-warning-soft text-status-warning'
              : 'border-edge-subtle text-content-muted hover:border-edge hover:text-content-secondary hover:bg-surface-tertiary'
          }`}
        >
          <RotateCcw className="h-3 w-3" />
          <span>Amend</span>
        </button>
      </div>
    </div>
  )
}
