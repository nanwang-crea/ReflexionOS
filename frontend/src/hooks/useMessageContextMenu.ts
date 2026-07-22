// 聊天消息（用户消息 / 助手消息）右键复制菜单的公共 hook。
// 复制语义（对齐设计文档 docs/superpowers/specs/2026-07-22-chat-message-context-menu-design.md）：
// 有选区时复制可见文本（window.getSelection()），不区分消息类型；
// 无选区时复制 getFullText() 的返回值——调用方按消息类型传入全文或原始 Markdown。
import type { MouseEvent } from 'react'
import { useContextMenuStore } from '@/shared/stores/contextMenu.store'
import { showToast } from './useToast'

export function useMessageContextMenu(getFullText: () => string) {
  return (event: MouseEvent) => {
    event.preventDefault()

    const selection = window.getSelection()
    const selectedText = selection && !selection.isCollapsed ? selection.toString() : ''
    const textToCopy = selectedText || getFullText()

    useContextMenuStore.getState().open(event.clientX, event.clientY, [
      {
        label: '复制',
        onClick: async () => {
          try {
            await navigator.clipboard.writeText(textToCopy)
            showToast('info', '已复制到剪贴板', 2000)
          } catch {
            showToast('error', '复制失败')
          }
        },
      },
    ])
  }
}
