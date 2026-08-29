// 聊天消息（用户消息 / 助手消息）右键复制菜单的公共 hook。
// 复制语义（对齐设计文档 docs/superpowers/specs/2026-07-22-chat-message-context-menu-design.md）：
// 有选区时复制可见文本（window.getSelection()），不区分消息类型；
// 无选区时复制 getFullText() 的返回值——调用方按消息类型传入全文或原始 Markdown。
import type { MouseEvent } from 'react'
import { useContextMenuStore } from '@/shared/stores/contextMenu.store'
import { showToast } from './useToast'

// 函数名：useMessageContextMenu
// 入参：
//   - getFullText (() => string): 调用方提供的取全文回调，按消息类型返回全文或原始 Markdown
// 功能：生成消息右键菜单的事件处理函数，菜单项仅含“复制”
// 运行逻辑：
//   1. 阻止浏览器默认右键菜单
//   2. 若当前有非空选区，复制选区可见文本；否则调用 getFullText() 取全文
//   3. 通过 contextMenu.store 在鼠标位置弹出自定义菜单
//   4. 点击“复制”后写入系统剪贴板并弹出成功/失败提示
// 出参：(event: MouseEvent) => void - 可直接绑定到 onContextMenu 的事件处理函数
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
