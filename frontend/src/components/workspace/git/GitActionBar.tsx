/**
 * 文件功能：Git 操作工具栏组件
 * 文件描述：提供 push / pull / fetch / stash / stash pop 等常用 Git 操作按钮，位于 Git 面板底部
 * 核心逻辑：直接从 useGitStore 读取对应的异步操作方法和加载态标志，点击按钮时调用 store 中的方法，按钮在对应操作进行中会禁用并显示加载文案
 */
import { ArrowUp, ArrowDown, Archive, ArchiveRestore, CloudDownload } from 'lucide-react'
import { useGitStore } from '@/features/git/stores/git.store'

/**
 * 函数名：GitActionBar
 * 入参：无（不接收 props）
 * 功能：渲染 Git 操作工具栏，包含 Push、Pull、Fetch 以及 Stash / Stash Pop 按钮
 * 运行逻辑：
 *   1. 从 useGitStore 中取出 push/pull/stash/fetchRemote 等操作函数，以及 isPushing/isPulling/isFetching 加载状态
 *   2. 渲染 Push、Pull 按钮，操作进行中时禁用并显示省略号，操作完成后显示对应文案
 *   3. 渲染 Fetch 图标按钮，进行中时禁用
 *   4. 渲染右侧的 Stash（贮藏）与 Stash Pop（恢复贮藏）图标按钮
 * 出参：JSX.Element - Git 操作工具栏的 DOM 结构
 */
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
