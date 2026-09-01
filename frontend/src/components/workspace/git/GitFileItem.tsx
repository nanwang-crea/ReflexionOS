/**
 * 文件功能：单个 Git 变更文件条目组件
 * 文件描述：展示单个文件的名称、增删行数统计、状态码，并提供打开 diff、暂存/取消暂存/丢弃变更等操作入口
 * 核心逻辑：点击文件名以 diff 模式打开该文件；根据 section 类型渲染不同的悬浮操作按钮（已暂存显示"取消暂存"，未暂存/未跟踪显示"暂存"和"丢弃变更"）；丢弃变更后弹出提示
 */
import { File, Plus, Minus, RotateCcw } from 'lucide-react'
import type { GitStatusCode } from '@/types/git'
import { useCodeTabStore } from '@/features/code/stores/codeTab.store'
import { useGitStore } from '@/features/git/stores/git.store'
import { useToast } from '@/hooks/useToast'

// Git 状态码到文字颜色样式的映射：M（修改）/A（新增）显示成功色，D（删除）显示错误色，U（未合并）显示灰色，R（重命名）显示强调色
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

/**
 * 函数名：GitFileItem
 * 入参：GitFileItemProps
 *   - path (string): 文件的完整相对路径
 *   - status (GitStatusCode): Git 状态码（M/A/D/U/R）
 *   - insertions (number | null 可选): 新增行数
 *   - deletions (number | null 可选): 删除行数
 *   - section ('staged' | 'unstaged' | 'untracked'): 所属分组类型，决定渲染哪些操作按钮
 * 功能：渲染单个文件变更条目，包含文件图标、文件名、增删统计、状态码和操作按钮
 * 运行逻辑：
 *   1. 从 useCodeTabStore 获取 openFile 方法，从 useGitStore 获取 stageFiles/unstageFiles/discardChanges 方法，从 useToast 获取提示方法
 *   2. 从完整路径中提取文件名用于展示
 *   3. handleOpenFile：以 'diff' 模式打开该文件对比视图
 *   4. handleStage / handleUnstage：分别调用 stageFiles / unstageFiles 对当前文件执行暂存/取消暂存
 *   5. handleDiscard：调用 discardChanges 丢弃当前文件的变更，并通过 toast 显示"已丢弃变更"提示
 *   6. 渲染文件图标、可点击文件名（悬浮显示完整路径）、增删行数统计、状态码文字（按 GIT_STATUS_STYLES 着色）
 *   7. 根据 section 渲染对应操作按钮：staged 显示"取消暂存"；unstaged/untracked 显示"暂存"和"丢弃变更"
 * 出参：JSX.Element - 单个文件条目的 DOM 结构
 */
export function GitFileItem({ path, status, insertions, deletions, section }: GitFileItemProps) {
  const openFile = useCodeTabStore((s) => s.openFile)
  const stageFiles = useGitStore((s) => s.stageFiles)
  const unstageFiles = useGitStore((s) => s.unstageFiles)
  const discardChanges = useGitStore((s) => s.discardChanges)
  const toast = useToast()

  const filename = path.split('/').pop() ?? path

  // 以 diff 模式打开当前文件，供用户查看具体改动内容
  const handleOpenFile = () => {
    openFile(path, 'diff')
  }

  // 将当前文件加入暂存区
  const handleStage = () => {
    stageFiles([path])
  }

  // 将当前文件从暂存区移除
  const handleUnstage = () => {
    unstageFiles([path])
  }

  // 丢弃当前文件的未提交变更，并通过 toast 提示用户已丢弃
  const handleDiscard = async () => {
    discardChanges([path])
    toast.showInfo('已丢弃变更: ' + filename)
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
