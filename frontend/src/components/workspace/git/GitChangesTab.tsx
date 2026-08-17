/**
 * 文件功能：工作区 Git 变更总面板
 * 文件描述：组合分支栏、已暂存/已修改/未跟踪文件分组、提交输入框、操作工具栏和提交历史面板，构成 Git 侧栏"变更"标签页的完整视图
 * 核心逻辑：挂载时拉取一次 Git 状态；根据 store 中的加载态/是否为 Git 仓库分别渲染加载中提示、非 Git 仓库提示或完整的变更管理界面；提交历史面板通过本地状态控制展开/收起
 */
import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, History, GitBranch } from 'lucide-react'
import { useGitStore } from '@/features/git/stores/git.store'
import { GitBranchBar } from './GitBranchBar'
import { GitFileGroup } from './GitFileGroup'
import { GitCommitInput } from './GitCommitInput'
import { GitActionBar } from './GitActionBar'
import { GitLogPanel } from './GitLogPanel'

/**
 * 函数名：NotGitRepo
 * 入参：无
 * 功能：渲染"当前项目目录未初始化为 Git 仓库"的提示视图
 * 运行逻辑：纯展示型组件，无交互逻辑，仅显示图标和引导文案
 * 出参：JSX.Element - 提示信息的 DOM 结构
 */
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

/**
 * 函数名：GitChangesTab
 * 入参：无（不接收 props）
 * 功能：渲染 Git 变更管理标签页的整体布局，包括分支栏、文件分组、提交输入、操作栏与提交历史
 * 运行逻辑：
 *   1. 从 useGitStore 读取分支信息、三类文件列表（已暂存/已修改/未跟踪）、分组展开状态、加载态和是否为 Git 仓库标志
 *   2. 使用本地状态 showLog 控制提交历史面板的展开/收起
 *   3. 组件挂载时调用 fetchStatus 拉取一次最新 Git 状态
 *   4. 若处于加载中且尚无分支信息、且已知为 Git 仓库，展示"加载中..."提示
 *   5. 若当前目录不是 Git 仓库，渲染 NotGitRepo 提示视图
 *   6. 否则渲染完整界面：分支栏 -> 已暂存/已修改/未跟踪三个文件分组 -> 提交输入框 -> 操作工具栏 -> 可展开的提交历史面板
 * 出参：JSX.Element - 变更管理标签页的 DOM 结构
 */
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

  // 组件挂载时拉取一次 Git 状态（分支信息、变更文件列表等）
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
