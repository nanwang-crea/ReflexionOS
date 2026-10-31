// 文件功能：消息发送队列条组件
// 文件描述：渲染当前会话的排队消息列表（Agent 回复中用户继续提交的消息），支持逐条编辑、
//          删除、插队（立即发送），以及队列暂停后的恢复；数据来自后端 conversation:queue_state
//          广播的全量快照，位于输入框上方（AgentWorkspace 输入区内）。
// 核心逻辑：queue 为空或（无排队项且未暂停）时不渲染；每条排队项提供行内编辑
//          （点击内容进入编辑态，Enter/失焦保存、Esc 取消）、立即发送（移到队首并尝试发起）、
//          删除三种操作；paused 时展示暂停横幅与恢复按钮。
import { useEffect, useRef, useState } from 'react'
import { ListOrdered, Pencil, Play, Trash2, X } from 'lucide-react'
import type { MessageQueueState } from '@/types/conversation'

interface MessageQueueBarProps {
  queue: MessageQueueState | null
  onUpdate: (queueId: string, content: string) => void
  onRemove: (queueId: string) => void
  onSendNow: (queueId: string) => void
  onResume: () => void
}

/**
 * 函数名：MessageQueueBar
 * 入参：queue - 会话队列全量快照（null 表示尚未收到广播）；onUpdate/onRemove/onSendNow/onResume - 队列操作回调
 * 功能：渲染排队消息条（列表 + 暂停横幅），把用户的编辑/删除/立即发送/恢复操作转发给回调
 * 运行逻辑：
 *   1. queue 为 null 或（items 为空且未暂停）时返回 null，不占布局；
 *   2. 每条排队项行内展示序号与内容，点击内容进入编辑态：Enter 或失焦保存，Esc 取消；
 *   3. paused 时显示暂停说明（通常是用户取消了运行）与"恢复队列"按钮。
 * 出参：JSX.Element | null - 队列条，或无需展示时为 null
 */
export function MessageQueueBar({
  queue,
  onUpdate,
  onRemove,
  onSendNow,
  onResume,
}: MessageQueueBarProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingValue, setEditingValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    // 正在编辑的排队项被发送/删除后（快照中消失），自动退出编辑态
    if (editingId && queue && !queue.items.some((item) => item.id === editingId)) {
      setEditingId(null)
    }
  }, [queue, editingId])

  useEffect(() => {
    if (editingId) {
      textareaRef.current?.focus()
    }
  }, [editingId])

  if (!queue || (queue.items.length === 0 && !queue.paused)) {
    return null
  }

  const startEdit = (queueId: string, content: string) => {
    setEditingId(queueId)
    setEditingValue(content)
  }

  const commitEdit = () => {
    if (!editingId) return
    const next = editingValue.trim()
    if (next) {
      onUpdate(editingId, next)
    }
    setEditingId(null)
  }

  return (
    <div
      data-message-queue-bar
      className="mb-3 rounded-2xl border border-edge bg-surface-secondary px-3 py-2"
    >
      <div className="mb-1 flex items-center gap-2 text-xs font-medium text-content-secondary">
        <ListOrdered className="h-3.5 w-3.5" />
        <span>待发送队列（回复结束后自动按序执行）</span>
      </div>

      {queue.paused && (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-xl bg-amber-500/10 px-3 py-1.5 text-xs text-amber-600 dark:text-amber-400">
          <span>队列已暂停（运行被取消），恢复后将按序发送排队消息</span>
          <button
            type="button"
            onClick={onResume}
            className="shrink-0 rounded-full bg-amber-500/15 px-2.5 py-0.5 font-medium text-amber-600 transition hover:bg-amber-500/25 dark:text-amber-400"
          >
            恢复队列
          </button>
        </div>
      )}

      <ul className="flex flex-col gap-1">
        {queue.items.map((item, index) => (
          <li
            key={item.id}
            data-queue-item={item.id}
            className="group flex items-start gap-2 rounded-xl bg-surface-primary px-2.5 py-1.5"
          >
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-tertiary text-[11px] font-semibold text-content-secondary">
              {index + 1}
            </span>
            {editingId === item.id ? (
              <textarea
                ref={textareaRef}
                value={editingValue}
                onChange={(e) => setEditingValue(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.nativeEvent.isComposing) return
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    commitEdit()
                  } else if (e.key === 'Escape') {
                    e.preventDefault()
                    setEditingId(null)
                  }
                }}
                rows={2}
                className="min-h-[40px] flex-1 resize-none rounded-lg border border-edge bg-surface-primary px-2 py-1 text-sm text-content-secondary outline-none focus:border-accent"
              />
            ) : (
              <button
                type="button"
                onClick={() => startEdit(item.id, item.content)}
                title="点击编辑这条排队消息"
                className="flex-1 whitespace-pre-wrap break-all text-left text-sm text-content-secondary transition hover:text-content-primary"
              >
                {item.content}
              </button>
            )}
            <span className="flex shrink-0 items-center gap-1 opacity-0 transition group-hover:opacity-100">
              <button
                type="button"
                onClick={() => onSendNow(item.id)}
                title="立即发送（移到队首，回复结束后优先执行）"
                className="rounded-full p-1.5 text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary"
              >
                <Play className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => startEdit(item.id, item.content)}
                title="编辑"
                className="rounded-full p-1.5 text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onRemove(item.id)}
                title="从队列中删除"
                className="rounded-full p-1.5 text-content-muted transition hover:bg-red-500/10 hover:text-red-500"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </span>
          </li>
        ))}
      </ul>

      {editingId && (
        <button
          type="button"
          onClick={() => setEditingId(null)}
          className="mt-1 flex items-center gap-1 text-xs text-content-muted transition hover:text-content-secondary"
        >
          <X className="h-3 w-3" />
          取消编辑（Esc）
        </button>
      )}
    </div>
  )
}
