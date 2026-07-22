// 应用内自绘右键菜单。
// ContextMenu 是纯展示组件，不持有业务状态；ContextMenuHost 订阅 contextMenu.store 渲染它
// （对齐 ConfirmDialog.tsx / ConfirmDialogHost 的拆分方式，展示组件可脱离 store 单独测试）。
// 挂载在 App.tsx 顶层，与 ConfirmDialogHost、ToastContainer 并列。
// 视觉风格对齐 ConfirmDialog.tsx：framer-motion 淡入淡出 + Esc 关闭。
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useContextMenuStore, type ContextMenuItem } from '@/shared/stores/contextMenu.store'

interface ContextMenuProps {
  isOpen: boolean
  x: number
  y: number
  items: ContextMenuItem[]
  onClose: () => void
}

export function ContextMenu({ isOpen, x, y, items, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  // 反弹后的实际渲染坐标；未测量前先用原始点击坐标，测量后如超出边界则改为反向定位。
  const [position, setPosition] = useState({ left: x, top: y })

  useEffect(() => {
    if (!isOpen) return
    setPosition({ left: x, top: y })
  }, [isOpen, x, y])

  useEffect(() => {
    if (!isOpen || !menuRef.current) return
    const rect = menuRef.current.getBoundingClientRect()
    const nextLeft = x + rect.width > window.innerWidth ? Math.max(0, x - rect.width) : x
    const nextTop = y + rect.height > window.innerHeight ? Math.max(0, y - rect.height) : y
    if (nextLeft !== x || nextTop !== y) {
      setPosition({ left: nextLeft, top: nextTop })
    }
  }, [isOpen, x, y, items])

  useEffect(() => {
    if (!isOpen) return

    const handleMouseDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) {
        onClose()
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }

    document.addEventListener('mousedown', handleMouseDown)
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onClose])

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          ref={menuRef}
          className="fixed z-[70] min-w-[120px] rounded-md border border-edge bg-surface-primary py-1 shadow-theme"
          style={{ left: position.left, top: position.top }}
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.12 }}
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              className="block w-full px-3 py-1.5 text-left text-sm text-content-secondary hover:bg-surface-tertiary"
              onClick={() => {
                onClose()
                item.onClick()
              }}
            >
              {item.label}
            </button>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// 宿主：订阅 store，把状态接到展示组件，并把关闭事件接回 store.close。
export function ContextMenuHost() {
  const { isOpen, x, y, items } = useContextMenuStore()

  return (
    <ContextMenu
      isOpen={isOpen}
      x={x}
      y={y}
      items={items}
      onClose={() => useContextMenuStore.getState().close()}
    />
  )
}
