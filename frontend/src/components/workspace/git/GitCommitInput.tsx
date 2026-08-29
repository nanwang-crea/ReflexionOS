/**
 * 文件功能：Git 提交信息输入组件
 * 文件描述：提供提交信息文本框、Commit 按钮及 Amend（修补上一次提交）切换按钮
 * 核心逻辑：根据是否有已暂存文件（或处于 amend 模式）及提交信息是否非空，决定 Commit 按钮是否可用；支持 Ctrl/Cmd+Enter 快捷提交
 */
import { Check, RotateCcw } from 'lucide-react'
import { useGitStore } from '@/features/git/stores/git.store'
import { useState } from 'react'

/**
 * 函数名：GitCommitInput
 * 入参：无（不接收 props）
 * 功能：渲染提交信息输入框以及 Commit / Amend 操作按钮
 * 运行逻辑：
 *   1. 从 useGitStore 读取提交信息文本、setCommitMessage、commit 方法、已暂存文件列表和提交中状态
 *   2. 本地状态 amend 控制是否处于"修补上一次提交"模式
 *   3. canCommit 计算是否允许提交：需要有已暂存文件（或处于 amend 模式）、提交信息非空、且当前不在提交中
 *   4. handleCommit 在允许提交时调用 commit 方法提交，若是 amend 模式提交后自动退出 amend 模式
 *   5. handleKeyDown 监听 Ctrl/Cmd+Enter 组合键，满足可提交条件时触发提交并阻止默认换行行为
 *   6. 渲染文本域（placeholder 根据 amend 状态变化）、Commit 按钮（禁用态样式区分）与 Amend 切换按钮
 * 出参：JSX.Element - 提交输入区域的 DOM 结构
 */
export function GitCommitInput() {
  const commitMessage = useGitStore((s) => s.commitMessage)
  const setCommitMessage = useGitStore((s) => s.setCommitMessage)
  const commit = useGitStore((s) => s.commit)
  const stagedFiles = useGitStore((s) => s.stagedFiles)
  const isCommitting = useGitStore((s) => s.isCommitting)

  const [amend, setAmend] = useState(false)
  const canCommit = (stagedFiles.length > 0 || amend) && commitMessage.trim().length > 0 && !isCommitting

  // 执行提交：条件不满足时直接返回；否则调用 commit 方法提交去除首尾空白后的提交信息，amend 模式提交后自动关闭
  const handleCommit = () => {
    if (!canCommit) return
    commit(commitMessage.trim(), amend)
    if (amend) setAmend(false)
  }

  // 监听键盘事件：按下 Ctrl/Cmd+Enter 且满足可提交条件时，阻止默认行为并触发提交
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
