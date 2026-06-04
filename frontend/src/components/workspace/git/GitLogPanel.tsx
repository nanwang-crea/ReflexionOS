import { GitCommitHorizontal, RefreshCw } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'
import { useEffect } from 'react'

export function GitLogPanel() {
  const logCommits = useGitStore((s) => s.logCommits)
  const isLoadingLog = useGitStore((s) => s.isLoadingLog)
  const fetchLog = useGitStore((s) => s.fetchLog)

  useEffect(() => {
    fetchLog()
  }, [fetchLog])

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-3 py-1.5 text-xs text-content-secondary">
        <span className="flex items-center gap-1.5 font-medium">
          <GitCommitHorizontal className="h-3 w-3 text-content-muted" />
          历史
        </span>
        <button
          type="button"
          onClick={() => fetchLog()}
          disabled={isLoadingLog}
          className="rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary disabled:opacity-50"
          title="刷新"
        >
          <RefreshCw className={`h-3 w-3 ${isLoadingLog ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {isLoadingLog && logCommits.length === 0 ? (
        <div className="px-3 py-3 text-center text-xs text-content-muted">加载中...</div>
      ) : logCommits.length === 0 ? (
        <div className="px-3 py-3 text-center text-xs text-content-muted">暂无提交</div>
      ) : (
        <div className="max-h-52 overflow-y-auto">
          {logCommits.map((c) => (
            <div
              key={c.hash}
              className="px-3 py-1.5 hover:bg-surface-tertiary border-t border-edge-subtle first:border-t-0"
            >
              <div className="flex items-start gap-2">
                <span className="mt-0.5 shrink-0 rounded bg-surface-tertiary px-1.5 py-0.5 font-mono text-[10px] leading-none text-content-muted">
                  {c.short_hash}
                </span>
                <span className="truncate text-xs leading-relaxed text-content-primary">{c.message}</span>
              </div>
              <div className="mt-0.5 pl-[52px] text-[10px] text-content-muted">
                {c.author} · {_formatDate(c.date)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function _formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)
    if (diffMin < 1) return '刚刚'
    if (diffMin < 60) return `${diffMin}分钟前`
    const diffHour = Math.floor(diffMin / 60)
    if (diffHour < 24) return `${diffHour}小时前`
    const diffDay = Math.floor(diffHour / 24)
    if (diffDay < 30) return `${diffDay}天前`
    return d.toLocaleDateString()
  } catch {
    return dateStr
  }
}
