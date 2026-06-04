import { GitBranch, ArrowUp, ArrowDown, ChevronDown, Plus, Trash2, X } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'
import { useState, useRef, useEffect } from 'react'

export function GitBranchBar() {
  const branchInfo = useGitStore((s) => s.branchInfo)
  const branches = useGitStore((s) => s.branches)
  const showBranchPicker = useGitStore((s) => s.showBranchPicker)
  const setShowBranchPicker = useGitStore((s) => s.setShowBranchPicker)
  const fetchBranches = useGitStore((s) => s.fetchBranches)
  const switchBranch = useGitStore((s) => s.switchBranch)
  const createBranch = useGitStore((s) => s.createBranch)
  const deleteBranch = useGitStore((s) => s.deleteBranch)

  const [newBranchName, setNewBranchName] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowBranchPicker(false)
        setShowCreate(false)
      }
    }
    if (showBranchPicker) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showBranchPicker, setShowBranchPicker])

  if (!branchInfo) return null

  const localBranches = branches.filter((b) => !b.is_remote)

  const handleToggle = () => {
    const next = !showBranchPicker
    setShowBranchPicker(next)
    if (next) fetchBranches()
  }

  const handleCreate = () => {
    const name = newBranchName.trim()
    if (!name) return
    createBranch(name)
    setNewBranchName('')
    setShowCreate(false)
  }

  return (
    <div className="relative border-b border-edge-subtle" ref={pickerRef}>
      <button
        type="button"
        onClick={handleToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-content-secondary hover:bg-surface-tertiary"
      >
        <GitBranch className="h-3.5 w-3.5 shrink-0 text-content-muted" />
        <span className="truncate font-medium">{branchInfo.name}</span>
        <ChevronDown className={`shrink-0 h-3 w-3 text-content-muted transition-transform ${showBranchPicker ? 'rotate-180' : ''}`} />
        <span className="ml-auto flex items-center gap-1 text-content-muted">
          {branchInfo.ahead > 0 && <span className="flex items-center gap-0.5"><ArrowUp className="h-3 w-3" />{branchInfo.ahead}</span>}
          {branchInfo.behind > 0 && <span className="flex items-center gap-0.5"><ArrowDown className="h-3 w-3" />{branchInfo.behind}</span>}
        </span>
      </button>

      {showBranchPicker && (
        <div className="absolute left-0 right-0 top-full z-20 max-h-60 overflow-y-auto rounded-b-md border border-edge bg-surface-primary shadow-lg">
          <div className="p-1">
            {localBranches.map((b) => (
              <div
                key={b.name}
                className="group flex items-center rounded px-2 py-1 text-xs hover:bg-surface-tertiary"
              >
                <button
                  type="button"
                  onClick={() => { if (!b.is_current) switchBranch(b.name) }}
                  disabled={b.is_current}
                  className={`flex-1 truncate text-left ${b.is_current ? 'font-medium text-accent' : 'text-content-secondary'}`}
                >
                  {b.is_current ? '✓ ' : '  '}{b.name}
                </button>
                {!b.is_current && (
                  <button
                    type="button"
                    onClick={() => deleteBranch(b.name)}
                    className="shrink-0 rounded p-0.5 text-content-muted opacity-0 group-hover:opacity-100 hover:text-status-error"
                    title="删除分支"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))}
          </div>

          <div className="border-t border-edge-subtle p-1.5">
            {showCreate ? (
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  value={newBranchName}
                  onChange={(e) => setNewBranchName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') { setShowCreate(false); setNewBranchName('') } }}
                  placeholder="新分支名称"
                  className="min-w-0 flex-1 rounded border border-edge-subtle bg-surface-primary px-2 py-1 text-xs text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={!newBranchName.trim()}
                  className="shrink-0 rounded px-2 py-1 text-xs font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-40"
                >
                  创建
                </button>
                <button
                  type="button"
                  onClick={() => { setShowCreate(false); setNewBranchName('') }}
                  className="shrink-0 rounded p-1 text-content-muted hover:bg-surface-tertiary"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowCreate(true)}
                className="flex w-full items-center justify-center gap-1 rounded px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary"
              >
                <Plus className="h-3 w-3" />
                新建分支
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
