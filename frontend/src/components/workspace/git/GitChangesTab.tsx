import { useGitStore } from '@/features/git/gitStore'
import { GitBranchBar } from './GitBranchBar'
import { GitFileGroup } from './GitFileGroup'
import { GitCommitInput } from './GitCommitInput'
import { GitActionBar } from './GitActionBar'

export function GitChangesTab() {
  const branchInfo = useGitStore((s) => s.branchInfo)
  const stagedFiles = useGitStore((s) => s.stagedFiles)
  const unstagedFiles = useGitStore((s) => s.unstagedFiles)
  const untrackedFiles = useGitStore((s) => s.untrackedFiles)
  const stagedCollapsed = useGitStore((s) => s.stagedCollapsed)
  const unstagedCollapsed = useGitStore((s) => s.unstagedCollapsed)
  const toggleStagedCollapsed = useGitStore((s) => s.toggleStagedCollapsed)
  const toggleUnstagedCollapsed = useGitStore((s) => s.toggleUnstagedCollapsed)
  const isLoading = useGitStore((s) => s.isLoading)

  if (isLoading && !branchInfo) {
    return (
      <div className="flex-1 px-3 py-4 text-xs text-content-muted">
        加载中...
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <GitBranchBar />
      <GitFileGroup
        title="Staged Changes"
        files={stagedFiles}
        section="staged"
        collapsed={stagedCollapsed}
        onToggleCollapsed={toggleStagedCollapsed}
      />
      <GitFileGroup
        title="Changes"
        files={unstagedFiles}
        section="unstaged"
        collapsed={unstagedCollapsed}
        onToggleCollapsed={toggleUnstagedCollapsed}
      />
      <GitFileGroup
        title="Untracked"
        files={untrackedFiles}
        section="untracked"
        collapsed={false}
        onToggleCollapsed={() => {}}
      />
      <GitCommitInput />
      <GitActionBar />
    </div>
  )
}
