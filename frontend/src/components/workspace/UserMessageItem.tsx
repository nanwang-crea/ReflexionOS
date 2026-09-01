/**
 * 文件功能：用户消息展示组件
 * 文件描述：展示单条用户消息，包括附件缩略图（图片预览/文件图标）、消息内容（支持编辑态输入框）、
 *          以及悬浮显示的复制/编辑操作按钮
 * 核心逻辑：非编辑态下右键消息可触发复制整条消息全文的上下文菜单；编辑态展示可编辑文本域与取消/发送按钮；
 *          附件路径按约定格式解析出 session_id 以拼装访问 URL，最多展示 4 个附件缩略图，超出部分显示数量角标
 */
import { memo } from 'react'
import { Copy, Pencil } from 'lucide-react'
import { useToastStore } from '@/shared/stores/toast.store'
import { useMessageContextMenu } from '@/hooks/useMessageContextMenu'

interface MessageAttachment {
  id: string
  type: string
  mimeType: string
  filePath: string
  fileSize: number
  createdAt: string
}

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
  attachments?: MessageAttachment[]
}

/**
 * 组件名：UserMessageItem
 * 入参（props，UserMessageItemProps）：
 *   - messageId (string): 消息唯一标识
 *   - contentText (string): 消息文本内容
 *   - onEdit ((messageId, contentText) => void): 点击编辑按钮时的回调
 *   - isEditing (boolean): 当前消息是否处于编辑态
 *   - editContent (string): 编辑态下文本框的内容
 *   - onEditContentChange ((content: string) => void): 编辑内容变化时的回调
 *   - onEditCancel (() => void): 取消编辑时的回调
 *   - onEditSubmit (() => void): 提交编辑（发送）时的回调
 *   - showActions (boolean): 是否显示悬浮操作按钮（复制/编辑）
 *   - attachments (MessageAttachment[]，可选): 消息携带的附件列表
 * 作用/渲染逻辑：
 *   1. 附件区：最多展示 4 个缩略图，图片类型直接预览，其余类型展示占位图标；超出 4 个展示 “+N” 角标
 *   2. 非编辑态：以气泡样式展示消息文本，支持右键复制全文；编辑态：展示可编辑文本域及取消/发送按钮
 *   3. 悬浮操作区（showActions 且非编辑态时展示）：复制按钮（写入剪贴板并 toast 提示）、编辑按钮
 * 返回值：JSX.Element - 用户消息气泡（含附件、内容、操作按钮）
 */
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
  attachments = [],
}: UserMessageItemProps) {
  // 用户消息无选区时复制整条消息全文
  const handleContextMenu = useMessageContextMenu(() => contentText)

  // 从 filePath 中提取 session_id 和 attachment_id
  const getImageUrl = (attachment: MessageAttachment) => {
    // filePath 格式: storage/uploads/{session_id}/{timestamp}_{file_id}.ext
    const pathParts = attachment.filePath.split('/')
    if (pathParts.length >= 3) {
      const sessionId = pathParts[2]
      return `/api/sessions/${sessionId}/attachments/${attachment.id}`
    }
    return ''
  }

  return (
    <div className="mb-6 flex min-w-0 flex-col items-end pr-8 group">
      {attachments.length > 0 && (
        <div className="mb-2 flex max-w-[min(720px,calc(100%_-_16px))] flex-wrap gap-1.5">
          {attachments.slice(0, 4).map((att) => (
            <div
              key={att.id}
              className="h-20 w-20 overflow-hidden rounded-lg border border-edge-subtle bg-surface-tertiary flex items-center justify-center"
            >
              {att.mimeType?.startsWith('image/') ? (
                <img
                  src={getImageUrl(att)}
                  alt="attachment"
                  className="h-full w-full object-cover"
                />
              ) : (
                <span className="text-xs text-content-muted">📎</span>
              )}
            </div>
          ))}
          {attachments.length > 4 && (
            <div className="flex h-20 w-20 items-center justify-center rounded-lg border border-edge-subtle bg-surface-tertiary text-sm text-content-muted">
              +{attachments.length - 4}
            </div>
          )}
        </div>
      )}
      {isEditing ? (
        <div className="w-full max-w-[min(720px,calc(100%_-_16px))]">
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
        <div
          className="max-w-[min(720px,calc(100%_-_16px))] whitespace-pre-wrap break-words rounded-2xl bg-surface-tertiary px-5 py-4 text-[15px] leading-7 text-content-secondary"
          onContextMenu={handleContextMenu}
        >
          {contentText}
        </div>
      )}
      {!isEditing && showActions && (
        <div className="mt-1 flex w-full max-w-[min(720px,calc(100%_-_16px))] justify-end gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
          <button
            type="button"
            className="inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors text-content-muted hover:bg-surface-tertiary hover:text-content-secondary"
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
            className="inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors text-content-muted hover:bg-surface-tertiary hover:text-content-secondary"
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
