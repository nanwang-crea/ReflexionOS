/**
 * 文件功能：Git 分支切换栏组件
 * 文件描述：展示当前分支名称、领先/落后远端的提交数，并提供分支选择器（切换分支、新建分支、删除分支）
 * 核心逻辑：点击栏位展开/收起下拉分支列表；下拉列表内可切换当前分支、删除非当前分支、通过输入框新建分支；使用 ref + mousedown 监听实现点击外部关闭下拉框
 */
import { GitBranch, ArrowUp, ArrowDown, ChevronDown, Plus, Trash2, X } from 'lucide-react'
import { useGitStore } from '@/features/git/stores/git.store'
import { useState, useRef, useEffect } from 'react'

/**
 * 函数名：GitBranchBar
 * 入参：无（不接收 props）
 * 功能：渲染当前分支信息栏及可展开的分支选择/新建/删除面板
 * 运行逻辑：
 *   1. 从 useGitStore 读取分支信息（branchInfo）、分支列表（branches）、选择器展开状态等
 *   2. 使用本地状态管理"新建分支"输入框内容与展示态
 *   3. 通过 useEffect 监听全局 mousedown 事件，点击选择器外部区域时自动收起选择器
 *   4. branchInfo 为空时不渲染任何内容（尚未获取到分支信息）
 *   5. 顶部按钮点击后切换选择器展开状态，展开时触发 fetchBranches 拉取分支列表
 *   6. 选择器展开时渲染本地分支列表，可点击切换当前分支，非当前分支支持删除
 *   7. 底部区域根据 showCreate 状态渲染"新建分支"输入框或"新建分支"触发按钮
 * 出参：JSX.Element | null - 分支栏 DOM 结构；branchInfo 未加载时返回 null
 */
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

  // 监听 mousedown 事件：当选择器展开且点击发生在选择器 DOM 外部时，收起选择器和新建分支输入框
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

  // 切换分支选择器展开/收起；展开时触发 fetchBranches 刷新分支列表
  const handleToggle = () => {
    const next = !showBranchPicker
    setShowBranchPicker(next)
    if (next) fetchBranches()
  }

  // 提交新建分支：去除首尾空白后校验非空，调用 createBranch 创建分支，随后清空输入框并收起创建面板
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
