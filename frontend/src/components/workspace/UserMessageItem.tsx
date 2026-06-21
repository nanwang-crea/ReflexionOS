import { memo } from 'react'
import { Copy, Pencil } from 'lucide-react'
import { useToastStore } from '@/shared/stores/toast.store'

interface UserMessageItemProps {
  messageId: string
  contentText: string
  onEdit: (messageId: string, contentText: string) => void
  isEditing: boolean
  editContent: string
  onEditContentChange: (content: string) => void
  onEditCancel: () => void
  onEditSubmit: () => void
  showActions: boolean
  attachments?: unknown[]
}

export const UserMessageItem = memo(function UserMessageItem({
  messageId,
  contentText,
  onEdit,
  isEditing,
  editContent,
  onEditContentChange,
  onEditCancel,
  onEditSubmit,
  showActions,
  attachments: _attachments,
}: UserMessageItemProps) {
  return (
    <div className="group mb-6 flex min-w-0 flex-col items-end pr-8">
      {isEditing ? (
        <div className="w-full max-w-[min(720px,calc(100%_-_16px))]">
          <textarea
            className="min-h-[60px] w-full resize-y rounded-2xl border border-edge bg-surface-tertiary px-5 py-4 text-[15px] leading-7 text-content-secondary focus:border-edge-active focus:outline-none"
            value={editContent}
            onChange={(e) => onEditContentChange(e.target.value)}
            autoFocus
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border border-edge px-3 py-1.5 text-xs text-content-muted transition-colors hover:border-edge-active hover:text-content-secondary"
              onClick={onEditCancel}
            >
              取消
            </button>
            <button
              type="button"
              className="rounded-lg bg-surface-tertiary px-3 py-1.5 text-xs text-content-secondary transition-colors hover:bg-surface-active"
              onClick={onEditSubmit}
            >
              发送
            </button>
          </div>
        </div>
      ) : (
        <div className="max-w-[min(720px,calc(100%_-_16px))] whitespace-pre-wrap break-words rounded-2xl bg-surface-tertiary px-5 py-4 text-[15px] leading-7 text-content-secondary">
          {contentText}
        </div>
      )}
      {!isEditing && showActions && (
        <div className="mt-1 flex w-full max-w-[min(720px,calc(100%_-_16px))] justify-end gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-content-muted transition-colors hover:bg-surface-tertiary hover:text-content-secondary"
            title="复制"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(contentText)
                useToastStore.getState().addToast('info', '已复制到剪贴板', 2000)
              } catch {
                useToastStore.getState().addToast('error', '复制失败')
              }
            }}
          >
            <Copy className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-content-muted transition-colors hover:bg-surface-tertiary hover:text-content-secondary"
            title="编辑"
            onClick={() => onEdit(messageId, contentText)}
          >
            <Pencil className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  )
})
