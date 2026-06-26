// 应用内自绘确认弹框。
// ConfirmDialog 是纯展示组件，不持有业务状态；ConfirmDialogHost 订阅 confirmDialog.store 渲染它。
// 设计：居中卡片 + 半透明遮罩，复用 Toast 的设计 token 与 framer-motion 动画，跨 macOS/Linux/Windows 一致。
// 键盘安全优先：打开时焦点落在「取消」，Esc/点遮罩=取消，Enter 跟随焦点（默认即取消），不做 Enter 全局映射。
import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle } from 'lucide-react'
import { useConfirmDialogStore, type ConfirmVariant } from '@/shared/stores/confirmDialog.store'

interface ConfirmDialogProps {
  open: boolean
  title?: string
  message: string
  variant: ConfirmVariant
  onConfirm: () => void
  onCancel: () => void
}

// 危险/默认两种变体的确认按钮配色（复用现有 status-error / accent token）。
const confirmButtonClass: Record<ConfirmVariant, string> = {
  danger: 'bg-status-error text-white hover:opacity-90',
  default: 'bg-accent text-white hover:opacity-90',
}

export function ConfirmDialog({ open, title, message, variant, onConfirm, onCancel }: ConfirmDialogProps) {
  // 取消按钮 ref：打开时把焦点移到这里（安全优先）。
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    // 打开后聚焦取消按钮。
    cancelRef.current?.focus()
    // Esc = 取消。仅在弹框打开时挂监听，关闭即移除，避免与全局快捷键冲突。
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCancel()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onCancel])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          // 半透明遮罩；点击空白处=取消。
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onMouseDown={(e) => {
            // 只在点到遮罩本身（非卡片内部）时取消。
            if (e.target === e.currentTarget) onCancel()
          }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            className="w-full max-w-sm rounded-lg border border-edge bg-surface-primary p-5 shadow-theme"
            initial={{ opacity: 0, y: -12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.96 }}
            transition={{ duration: 0.18 }}
          >
            <div className="flex items-start gap-3">
              {variant === 'danger' && (
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-status-error" />
              )}
              <div className="min-w-0 flex-1">
                {title && <h3 className="mb-1 text-base font-semibold text-content-primary">{title}</h3>}
                <p className="text-sm leading-6 text-content-secondary">{message}</p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                ref={cancelRef}
                type="button"
                onClick={onCancel}
                className="rounded-md px-3 py-1.5 text-sm text-content-secondary hover:bg-surface-tertiary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={onConfirm}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${confirmButtonClass[variant]}`}
              >
                确认
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// 宿主：订阅 store，把状态接到展示组件，并把按钮事件接回 store.resolveConfirm。
export function ConfirmDialogHost() {
  const { open, title, message, variant } = useConfirmDialogStore()
  const resolveConfirm = useConfirmDialogStore((s) => s.resolveConfirm)

  return (
    <ConfirmDialog
      open={open}
      title={title}
      message={message}
      variant={variant}
      onConfirm={() => resolveConfirm(true)}
      onCancel={() => resolveConfirm(false)}
    />
  )
}
