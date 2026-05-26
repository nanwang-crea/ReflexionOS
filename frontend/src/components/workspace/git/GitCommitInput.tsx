import { Check } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'

export function GitCommitInput() {
  const commitMessage = useGitStore((s) => s.commitMessage)
  const setCommitMessage = useGitStore((s) => s.setCommitMessage)
  const commit = useGitStore((s) => s.commit)
  const stagedFiles = useGitStore((s) => s.stagedFiles)
  const isCommitting = useGitStore((s) => s.isCommitting)

  const canCommit = stagedFiles.length > 0 && commitMessage.trim().length > 0 && !isCommitting

  const handleCommit = () => {
    if (!canCommit) return
    commit(commitMessage.trim())
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
        placeholder="Commit message..."
        rows={2}
        className="w-full resize-none rounded-md border border-edge-subtle bg-surface-primary px-2 py-1.5 text-sm text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none"
      />
      <button
        type="button"
        onClick={handleCommit}
        disabled={!canCommit}
        className={`mt-1.5 flex w-full items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          canCommit
            ? 'bg-accent text-white hover:bg-accent-hover'
            : 'bg-surface-tertiary text-content-muted cursor-not-allowed'
        }`}
      >
        <Check className="h-3.5 w-3.5" />
        {isCommitting ? '提交中...' : 'Commit'}
      </button>
    </div>
  )
}
