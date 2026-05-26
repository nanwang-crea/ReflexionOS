import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, History, GitBranch } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'
import { GitBranchBar } from './GitBranchBar'
import { GitFileGroup } from './GitFileGroup'
import { GitCommitInput } from './GitCommitInput'
import { GitActionBar } from './GitActionBar'
import { GitLogPanel } from './GitLogPanel'

function NotGitRepo() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-8">
      <GitBranch className="h-8 w-8 text-content-muted" />
      <div className="text-center">
        <p className="text-sm font-medium text-content-secondary">未初始化 Git 仓库</p>
        <p className="mt-1 text-xs text-content-muted">此项目目录尚未初始化为 Git 仓库。请在终端中运行 git init 开始版本管理。</p>
      </div>
    </div>
  )
}

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
  const notGitRepo = useGitStore((s) => s.notGitRepo)
  const fetchStatus = useGitStore((s) => s.fetchStatus)

  const [showLog, setShowLog] = useState(false)

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  if (isLoading && !branchInfo && !notGitRepo) {
    return (
      <div className="flex-1 px-3 py-4 text-xs text-content-muted">
        加载中...
      </div>
    )
  }

  if (notGitRepo) {
    return <NotGitRepo />
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <GitBranchBar />
      <GitFileGroup
        title="已暂存"
        files={stagedFiles}
        section="staged"
        collapsed={stagedCollapsed}
        onToggleCollapsed={toggleStagedCollapsed}
      />
      <GitFileGroup
        title="已修改"
        files={unstagedFiles}
        section="unstaged"
        collapsed={unstagedCollapsed}
        onToggleCollapsed={toggleUnstagedCollapsed}
      />
      <GitFileGroup
        title="未跟踪"
        files={untrackedFiles}
        section="untracked"
        collapsed={false}
        onToggleCollapsed={() => {}}
      />
      <GitCommitInput />
      <GitActionBar />
      <button
        type="button"
        onClick={() => setShowLog(!showLog)}
        className="flex items-center gap-1.5 border-t border-edge-subtle px-3 py-1.5 text-xs text-content-secondary hover:bg-surface-tertiary"
      >
        {showLog ? (
          <ChevronDown className="h-3 w-3 text-content-muted" />
        ) : (
          <ChevronRight className="h-3 w-3 text-content-muted" />
        )}
        <History className="h-3 w-3 text-content-muted" />
        <span>提交历史</span>
      </button>
      {showLog && <GitLogPanel />}
    </div>
  )
}
