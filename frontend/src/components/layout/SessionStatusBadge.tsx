// 会话状态徽标组件：把 sidebarSessionState 派生出的会话状态渲染成 sidebar 列表项上的小图标/文字提示。
// 覆盖同步异常、待审批、运行中、失败带未读、完成带未读五种状态；空闲状态不渲染任何内容，保持列表干净。
import { Loader2, TriangleAlert } from 'lucide-react'
import type { SidebarSessionStatus } from './sidebarSessionState'

// 把派生出的会话状态渲染成 sidebar 上的小徽标。
// 空闲且无未读时不渲染任何东西，保持列表干净。
// 参数：className - 圆点的颜色等样式类名。
// 返回：一个用 span 渲染的小圆点，作为状态指示器。
function StatusDot({ className }: { className: string }) {
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${className}`} />
}

// 参数：status - 由 deriveSidebarSessionState 计算出的会话状态枚举。
// 作用：根据不同状态渲染不同的图标/文字/配色，优先级从高到低依次判断并返回。
// 返回：对应状态的 JSX 徽标；状态为 idle（空闲无未读）时返回 null，不渲染任何内容。
export function SessionStatusBadge({ status }: { status: SidebarSessionStatus }) {
  if (status === 'sync_abnormal') {
    // 同步异常：连接断开未恢复，切回会强制补拉。用警告色提示但不等于 run 失败。
    return (
      <span className="flex shrink-0 items-center text-status-warning" title="同步异常，切回将重新拉取">
        <TriangleAlert className="h-3.5 w-3.5" />
      </span>
    )
  }

  if (status === 'waiting_for_approval') {
    // 待审批：最高优先级，用强调色文字提示用户需要处理。
    return (
      <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-accent" title="等待审批">
        <StatusDot className="bg-accent" />
        待审批
      </span>
    )
  }

  if (status === 'running') {
    return (
      <span className="flex shrink-0 items-center text-accent" title="运行中">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      </span>
    )
  }

  if (status === 'failed_with_unread_activity') {
    return (
      <span className="flex shrink-0 items-center" title="运行失败（有未读）">
        <StatusDot className="bg-status-error" />
      </span>
    )
  }

  if (status === 'completed_with_unread_activity') {
    return (
      <span className="flex shrink-0 items-center" title="有未读更新">
        <StatusDot className="bg-accent" />
      </span>
    )
  }

  return null
}
