/**
 * 文件功能：技能列表“加载更多”按钮组件
 * 文件描述：在技能列表底部展示一个“加载更多”按钮，无更多数据时不渲染任何内容。
 * 核心逻辑：hasMore 为 false 时直接返回 null；否则渲染按钮，点击时触发 onClick 回调。
 */
interface LoadMoreButtonProps {
  hasMore: boolean
  onClick: () => void
}

/**
 * 函数名：LoadMoreButton
 * 入参：
 *   - hasMore (boolean): 是否还有更多数据可加载
 *   - onClick (() => void): 点击按钮时触发的回调，通常用于拉取下一页数据
 * 功能：渲染“加载更多”按钮，供技能列表分页加载使用
 * 运行逻辑：hasMore 为 false 时不渲染（返回 null）；为 true 时渲染按钮，点击触发 onClick
 * 出参：JSX.Element | null - 按钮元素或 null
 */
export default function LoadMoreButton({ hasMore, onClick }: LoadMoreButtonProps) {
  if (!hasMore) return null

  return (
    <div className="mt-8 flex justify-center">
      <button
        onClick={onClick}
        className="rounded-2xl border border-edge bg-surface-tertiary px-6 py-3 text-sm font-medium text-content-primary transition-colors hover:bg-surface-secondary"
      >
        加载更多
      </button>
    </div>
  )
}
