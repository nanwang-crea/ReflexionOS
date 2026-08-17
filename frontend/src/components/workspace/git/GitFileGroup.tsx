/**
 * 文件功能：Git 文件分组组件
 * 文件描述：按"已暂存 / 已修改 / 未跟踪"三种分区展示文件变更列表，支持分组折叠、批量暂存/取消暂存/丢弃变更
 * 核心逻辑：根据 section 类型渲染不同的批量操作按钮（已暂存分组显示"全部取消暂存"，已修改/未跟踪分组显示"全部暂存"和"全部丢弃"）；文件列表为空时不渲染分组；折叠时隐藏文件明细列表
 */
import { ChevronDown, ChevronRight, Plus, Minus, RotateCcw } from 'lucide-react'
import type { GitFileChange } from '@/types/git'
import { isValidGitStatusCode } from '@/types/git'
import { GitFileItem } from './GitFileItem'
import { useGitStore } from '@/features/git/stores/git.store'

interface GitFileGroupProps {
  title: string
  files: GitFileChange[]
  section: 'staged' | 'unstaged' | 'untracked'
  collapsed: boolean
  onToggleCollapsed: () => void
}

/**
 * 函数名：GitFileGroup
 * 入参：GitFileGroupProps
 *   - title (string): 分组标题，如"已暂存"、"已修改"、"未跟踪"
 *   - files (GitFileChange[]): 该分组下的文件变更列表
 *   - section ('staged' | 'unstaged' | 'untracked'): 分组类型，决定渲染哪些批量操作按钮
 *   - collapsed (boolean): 分组是否处于折叠状态
 *   - onToggleCollapsed (() => void): 点击分组标题时切换折叠状态的回调
 * 功能：渲染一个可折叠的文件分组，包含标题栏（含批量操作按钮）和文件明细列表
 * 运行逻辑：
 *   1. 从 useGitStore 读取 stageAll/unstageAll/discardAll 批量操作方法
 *   2. 若 files 为空数组，直接返回 null，不渲染任何内容
 *   3. 渲染标题栏：点击可切换折叠图标（ChevronRight/ChevronDown）与文件数量
 *   4. 根据 section 渲染对应的批量操作按钮：staged 显示"取消全部暂存"；unstaged/untracked 显示"全部暂存"和"全部丢弃"
 *   5. 若未折叠，遍历 files 渲染 GitFileItem 列表，文件状态码非法时兜底为 'M'
 * 出参：JSX.Element | null - 文件分组的 DOM 结构；文件列表为空时返回 null
 */
export function GitFileGroup({ title, files, section, collapsed, onToggleCollapsed }: GitFileGroupProps) {
  const stageAll = useGitStore((s) => s.stageAll)
  const unstageAll = useGitStore((s) => s.unstageAll)
  const discardAll = useGitStore((s) => s.discardAll)

  if (files.length === 0) return null

  return (
    <div className="border-b border-edge-subtle">
      <div className="flex items-center px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-surface-tertiary">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="flex items-center gap-1.5 flex-1 min-w-0"
        >
          {collapsed ? (
            <ChevronRight className="h-3 w-3 shrink-0 text-content-muted" />
          ) : (
            <ChevronDown className="h-3 w-3 shrink-0 text-content-muted" />
          )}
          <span className="truncate">{title}</span>
          <span className="shrink-0 text-content-muted">({files.length})</span>
        </button>

        <div className="flex shrink-0 items-center gap-0.5 ml-1">
          {section === 'staged' && (
            <button
              type="button"
              onClick={() => unstageAll()}
              className="rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
              title="Unstage All"
            >
              <Minus className="h-3 w-3" />
            </button>
          )}
          {section === 'unstaged' && (
            <>
              <button
                type="button"
                onClick={() => stageAll()}
                className="rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
                title="Stage All"
              >
                <Plus className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => discardAll()}
                className="rounded p-0.5 text-content-muted hover:text-status-error hover:bg-surface-tertiary"
                title="Discard All"
              >
                <RotateCcw className="h-3 w-3" />
              </button>
            </>
          )}
          {section === 'untracked' && (
            <>
              <button
                type="button"
                onClick={() => stageAll()}
                className="rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
                title="Stage All"
              >
                <Plus className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => discardAll()}
                className="rounded p-0.5 text-content-muted hover:text-status-error hover:bg-surface-tertiary"
                title="Discard All"
              >
                <RotateCcw className="h-3 w-3" />
              </button>
            </>
          )}
        </div>
      </div>
      {!collapsed && (
        <div className="pb-1">
          {files.map((file) => (
            <GitFileItem
              key={file.path}
              path={file.path}
              status={isValidGitStatusCode(file.status) ? file.status : 'M'}
              insertions={file.insertions}
              deletions={file.deletions}
              section={section}
            />
          ))}
        </div>
      )}
    </div>
  )
}
