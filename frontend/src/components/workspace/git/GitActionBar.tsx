import { ArrowUp, ArrowDown, Archive, ArchiveRestore } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'
import { useState } from 'react'

export function GitActionBar() {
  const push = useGitStore((s) => s.push)
  const pull = useGitStore((s) => s.pull)
  const stash = useGitStore((s) => s.stash)
  const isPushing = useGitStore((s) => s.isPushing)
  const isPulling = useGitStore((s) => s.isPulling)
  const [showStashPop, setShowStashPop] = useState(false)

  return (
    <div className="flex items-center gap-1 px-3 py-2">
      <button
        type="button"
        onClick={() => push()}
        disabled={isPushing}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-50"
        title="Push"
      >
        <ArrowUp className="h-3.5 w-3.5" />
        {isPushing ? '...' : 'Push'}
      </button>
      <button
        type="button"
        onClick={() => pull()}
        disabled={isPulling}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-50"
        title="Pull"
      >
        <ArrowDown className="h-3.5 w-3.5" />
        {isPulling ? '...' : 'Pull'}
      </button>
      <div className="relative">
        <button
          type="button"
          onClick={() => {
            if (showStashPop) {
              stash('pop')
              setShowStashPop(false)
            } else {
              stash('push')
            }
          }}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
          title="Stash"
        >
          <Archive className="h-3.5 w-3.5" />
          Stash
        </button>
        <button
          type="button"
          onClick={() => setShowStashPop(!showStashPop)}
          className="ml-0.5 rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
          title="Stash Pop"
        >
          <ArchiveRestore className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}
