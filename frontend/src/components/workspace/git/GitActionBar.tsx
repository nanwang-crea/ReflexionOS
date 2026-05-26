import { ArrowUp, ArrowDown, Archive, ArchiveRestore, CloudDownload } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'

export function GitActionBar() {
  const push = useGitStore((s) => s.push)
  const pull = useGitStore((s) => s.pull)
  const stash = useGitStore((s) => s.stash)
  const fetchRemote = useGitStore((s) => s.fetchRemote)
  const isPushing = useGitStore((s) => s.isPushing)
  const isPulling = useGitStore((s) => s.isPulling)
  const isFetching = useGitStore((s) => s.isFetching)

  const btnCls = "flex items-center gap-1 rounded-md px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-50"
  const iconBtnCls = "rounded p-1 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"

  return (
    <div className="flex items-center gap-1 border-b border-edge-subtle px-3 py-1.5">
      <button type="button" onClick={() => push()} disabled={isPushing} className={btnCls} title="Push">
        <ArrowUp className="h-3.5 w-3.5" />{isPushing ? '...' : 'Push'}
      </button>
      <button type="button" onClick={() => pull()} disabled={isPulling} className={btnCls} title="Pull">
        <ArrowDown className="h-3.5 w-3.5" />{isPulling ? '...' : 'Pull'}
      </button>
      <button type="button" onClick={() => fetchRemote()} disabled={isFetching} className={iconBtnCls} title="Fetch">
        <CloudDownload className="h-3.5 w-3.5" />
      </button>
      <div className="ml-auto flex items-center">
        <button type="button" onClick={() => stash('push')} className={iconBtnCls} title="Stash">
          <Archive className="h-3.5 w-3.5" />
        </button>
        <button type="button" onClick={() => stash('pop')} className={iconBtnCls} title="Stash Pop">
          <ArchiveRestore className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
