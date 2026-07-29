import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, Info, AlertTriangle, X } from 'lucide-react'
import { forwardRef } from 'react'
import { useToastStore, type ToastItem as ToastData } from '@/shared/stores/toast.store'

const levelConfig: Record<string, { icon: typeof AlertCircle; bg: string; border: string; text: string }> = {
  error: { icon: AlertCircle, bg: 'bg-status-error-soft', border: 'border-status-error-border', text: 'text-status-error' },
  warning: { icon: AlertTriangle, bg: 'bg-status-warning-soft', border: 'border-status-warning-border', text: 'text-status-warning' },
  info: { icon: Info, bg: 'bg-accent-soft', border: 'border-edge', text: 'text-accent' },
}

const ToastItem = forwardRef<HTMLDivElement, { item: ToastData }>(function ToastItem(
  { item },
  ref,
) {
  const removeToast = useToastStore((s) => s.removeToast)
  const config = levelConfig[item.level] ?? levelConfig.info
  const Icon = config.icon

  return (
    <motion.div
      ref={ref}
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
        aria-label="关闭通知"
        onClick={() => removeToast(item.id)}
        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
      >
        <X className="h-4 w-4" />
      </button>
    </motion.div>
  )
})

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
