import { GitBranch, ArrowUp, ArrowDown } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'

export function GitBranchBar() {
  const branchInfo = useGitStore((s) => s.branchInfo)

  if (!branchInfo) return null

  return (
    <div className="flex items-center gap-2 border-b border-edge-subtle px-3 py-2 text-xs text-content-secondary">
      <GitBranch className="h-3.5 w-3.5 shrink-0 text-content-muted" />
      <span className="truncate font-medium">{branchInfo.name}</span>
      {(branchInfo.ahead > 0 || branchInfo.behind > 0) && (
        <span className="ml-auto flex items-center gap-1 text-content-muted">
          {branchInfo.ahead > 0 && (
            <span className="flex items-center gap-0.5">
              <ArrowUp className="h-3 w-3" />
              {branchInfo.ahead}
            </span>
          )}
          {branchInfo.behind > 0 && (
            <span className="flex items-center gap-0.5">
              <ArrowDown className="h-3 w-3" />
              {branchInfo.behind}
            </span>
          )}
        </span>
      )}
    </div>
  )
}
