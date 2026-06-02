import { memo } from 'react'
import { MessageActions } from './MessageActions'

interface UserMessageItemProps {
  messageId: string
  contentText: string
  onEdit: (messageId: string, contentText: string) => void
  onRegenerate: (messageId: string) => void
  isEditing: boolean
  editContent: string
  onEditContentChange: (content: string) => void
  onEditCancel: () => void
  onEditSubmit: () => void
  showActions: boolean
}

export const UserMessageItem = memo(function UserMessageItem({
  messageId,
  contentText,
  onEdit,
  onRegenerate,
  isEditing,
  editContent,
  onEditContentChange,
  onEditCancel,
  onEditSubmit,
  showActions,
}: UserMessageItemProps) {
  return (
    <div className="mb-6 flex flex-col items-end group">
      {isEditing ? (
        <div className="max-w-[720px] w-full">
          <textarea
            className="w-full rounded-2xl bg-surface-tertiary border border-edge px-5 py-4 text-[15px] leading-7 text-content-secondary resize-y min-h-[60px] focus:outline-none focus:border-edge-active"
            value={editContent}
            onChange={(e) => onEditContentChange(e.target.value)}
            autoFocus
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              className="rounded-lg border border-edge px-3 py-1.5 text-xs text-content-muted hover:text-content-secondary hover:border-edge-active transition-colors"
              onClick={onEditCancel}
            >
              取消
            </button>
            <button
              type="button"
              className="rounded-lg bg-surface-tertiary px-3 py-1.5 text-xs text-content-secondary hover:bg-surface-active transition-colors"
              onClick={onEditSubmit}
            >
              发送
            </button>
          </div>
        </div>
      ) : (
        <div className="max-w-[720px] rounded-2xl bg-surface-tertiary px-5 py-4 text-[15px] leading-7 text-content-secondary">
          {contentText}
        </div>
      )}
      {!isEditing && showActions && (
        <MessageActions
          messageId={messageId}
          contentText={contentText}
          messageType="user_message"
          onEdit={onEdit}
          onRegenerate={onRegenerate}
        />
      )}
    </div>
  )
})
