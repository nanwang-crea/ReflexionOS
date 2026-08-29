// 应用内 Toast 提示容器：订阅 toast.store，在页面顶部居中弹出一组消息条（error/warning/info 三种级别），
// 支持自动/手动关闭，使用 framer-motion 实现出入场动画。
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, Info, AlertTriangle, X } from 'lucide-react'
import { useToastStore, type ToastItem } from '@/shared/stores/toast.store'

// 各提示级别对应的图标与配色（背景/边框/文字），未知级别时在使用处兜底为 info。
const levelConfig: Record<string, { icon: typeof AlertCircle; bg: string; border: string; text: string }> = {
  error: { icon: AlertCircle, bg: 'bg-status-error-soft', border: 'border-status-error-border', text: 'text-status-error' },
  warning: { icon: AlertTriangle, bg: 'bg-status-warning-soft', border: 'border-status-warning-border', text: 'text-status-warning' },
  info: { icon: Info, bg: 'bg-accent-soft', border: 'border-edge', text: 'text-accent' },
}

// 参数：item - 单条 toast 数据（id、级别、消息内容等）。
// 作用：渲染单条 toast 提示，根据级别选取图标与配色，提供手动关闭按钮（点击调用 store.removeToast）。
// 返回：单条 toast 的 JSX（带 framer-motion 进出场动画）。
function ToastItem({ item }: { item: ToastItem }) {
  const removeToast = useToastStore((s) => s.removeToast)
  const config = levelConfig[item.level] ?? levelConfig.info
  const Icon = config.icon

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -12, scale: 0.96 }}
      transition={{ duration: 0.18 }}
      className={`flex items-start gap-2 rounded-lg border ${config.border} ${config.bg} px-4 py-3 shadow-theme ${config.text}`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="flex-1 text-sm leading-5">{item.message}</span>
      <button
        type="button"
        onClick={() => removeToast(item.id)}
        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
      >
        <X className="h-4 w-4" />
      </button>
    </motion.div>
  )
}

// 参数：无（内部通过 useToastStore 订阅全局 toast 列表）。
// 作用：固定在页面顶部居中位置，展示当前所有 toast 消息，用 AnimatePresence 处理列表增删的过渡动画。
// 返回：Toast 容器 JSX，供挂载在 App.tsx 顶层。
export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-4">
      <div className="pointer-events-auto flex w-full max-w-lg flex-col gap-2">
        <AnimatePresence mode="popLayout">
          {toasts.map((item) => (
            <ToastItem key={item.id} item={item} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
