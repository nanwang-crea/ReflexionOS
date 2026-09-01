/**
 * 文件功能：Git 提交历史面板组件
 * 文件描述：展示最近的提交记录列表（哈希、提交信息、作者、相对时间），支持手动刷新
 * 核心逻辑：挂载时自动拉取一次提交历史；根据加载态和列表是否为空分别渲染加载中/暂无提交/提交列表三种状态；内部提供相对时间格式化辅助函数
 */
import { GitCommitHorizontal, RefreshCw } from 'lucide-react'
import { useGitStore } from '@/features/git/stores/git.store'
import { useEffect } from 'react'

/**
 * 函数名：GitLogPanel
 * 入参：无（不接收 props）
 * 功能：渲染提交历史面板，包含标题栏（含刷新按钮）和提交列表
 * 运行逻辑：
 *   1. 从 useGitStore 读取提交记录列表 logCommits、加载中状态 isLoadingLog、拉取方法 fetchLog
 *   2. 组件挂载时调用 fetchLog 拉取一次提交历史
 *   3. 渲染标题栏，含刷新按钮，加载中时禁用按钮并旋转图标
 *   4. 若正在加载且列表为空，显示"加载中..."；若加载完成但列表为空，显示"暂无提交"；否则渲染提交列表
 *   5. 每条提交渲染短哈希、提交信息、作者和经过 _formatDate 格式化的相对时间
 * 出参：JSX.Element - 提交历史面板的 DOM 结构
 */
export function GitLogPanel() {
  const logCommits = useGitStore((s) => s.logCommits)
  const isLoadingLog = useGitStore((s) => s.isLoadingLog)
  const fetchLog = useGitStore((s) => s.fetchLog)

  // 组件挂载时拉取一次提交历史
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

/**
 * 函数名：_formatDate
 * 入参：
 *   - dateStr (string): ISO 格式的日期时间字符串
 * 功能：将提交时间格式化为相对当前时间的中文简短描述
 * 运行逻辑：
 *   1. 解析日期字符串并计算与当前时间的毫秒差
 *   2. 按差值大小依次判断：小于 1 分钟显示"刚刚"，小于 1 小时显示"N分钟前"，小于 24 小时显示"N小时前"，小于 30 天显示"N天前"
 *   3. 超过 30 天则回退为本地日期格式字符串
 *   4. 解析失败时捕获异常，直接返回原始字符串
 * 出参：string - 格式化后的相对时间文案，或原始字符串（解析失败时）
 */
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
