// 文件功能：变更聚合展示条（Changed Files）
// 文件描述：在一次 run 的过程分组尾部展示本轮实际变更的文件清单，默认折叠为
//          "变更了 N 个文件"，展开后逐条显示动作徽标与路径；点击文件路径可通过
//          onFileClick 回调（如在工作区代码面板打开该文件）
// 核心逻辑：files 为空不渲染；动作徽标按 created/modified/deleted/moved 映射中文与配色，
//          moved 额外展示 oldPath → path
import { useState } from 'react'
import { ChevronDown, ChevronRight, FileDiff } from 'lucide-react'
import type { ChangedFileAction, ChangedFileEntry } from '@/types/conversation'

interface ChangedFilesBarProps {
  files: ChangedFileEntry[]
  onFileClick?: (path: string) => void
}

const ACTION_META: Record<ChangedFileAction, { label: string; className: string }> = {
  created: { label: '新建', className: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' },
  modified: { label: '修改', className: 'bg-blue-500/15 text-blue-600 dark:text-blue-400' },
  deleted: { label: '删除', className: 'bg-red-500/15 text-red-600 dark:text-red-400' },
  moved: { label: '移动', className: 'bg-purple-500/15 text-purple-600 dark:text-purple-400' },
}

/**
 * 函数名：ChangedFilesBar
 * 入参：files - 聚合后的变更条目；onFileClick - 点击文件路径的回调（可选）
 * 功能：渲染可折叠的变更清单条
 * 运行逻辑：本地 useState 控制展开态（默认折叠）；动作徽标样式由 ACTION_META 映射；
 *          onFileClick 缺省时路径为纯文本，提供时渲染为按钮
 * 出参：JSX.Element | null - 变更条，files 为空时返回 null
 */
export function ChangedFilesBar({ files, onFileClick }: ChangedFilesBarProps) {
  const [expanded, setExpanded] = useState(false)

  if (files.length === 0) {
    return null
  }

  return (
    <div
      data-changed-files-bar
      className="mb-2 rounded-xl border border-edge bg-surface-secondary/40 px-3 py-2"
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 text-sm text-content-secondary transition-colors hover:text-content-primary"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
        )}
        <FileDiff className="h-3.5 w-3.5 shrink-0" />
        <span>变更了 {files.length} 个文件</span>
      </button>

      {expanded && (
        <ul className="mt-2 flex flex-col gap-1">
          {files.map((file) => {
            const meta = ACTION_META[file.action] ?? ACTION_META.modified
            return (
              <li
                key={`${file.action}:${file.path}`}
                data-changed-file={file.path}
                className="flex items-center gap-2 rounded-lg bg-surface-primary px-2 py-1"
              >
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${meta.className}`}
                >
                  {meta.label}
                </span>
                {onFileClick ? (
                  <button
                    type="button"
                    onClick={() => onFileClick(file.path)}
                    title="在工作区打开该文件"
                    className="min-w-0 flex-1 truncate text-left font-mono text-xs text-content-secondary transition hover:text-accent"
                  >
                    {file.action === 'moved' && file.oldPath ? `${file.oldPath} → ${file.path}` : file.path}
                  </button>
                ) : (
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-content-secondary">
                    {file.action === 'moved' && file.oldPath ? `${file.oldPath} → ${file.path}` : file.path}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
