// 图片附件预览条组件：在聊天输入框上方展示待发送的图片附件缩略图列表，支持逐个移除。
// 用 memo 包裹以避免输入框内容变化时不必要的重渲染。
import { memo } from 'react'
import { X } from 'lucide-react'
import type { PendingAttachment } from '@/features/conversation/hooks/useImageUpload'

interface ImagePreviewProps {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
}

// 参数：attachments - 待发送的图片附件列表（含预览 URL）；onRemove - 点击移除按钮时的回调，传入附件 id。
// 作用：横向滚动展示每个附件的缩略图，悬停时显示右上角的删除按钮；附件列表为空时不渲染任何内容。
// 返回：附件列表为空时返回 null；否则返回横向滚动的缩略图列表 JSX。
export const ImagePreview = memo(function ImagePreview({
  attachments,
  onRemove,
}: ImagePreviewProps) {
  if (attachments.length === 0) return null

  return (
    <div className="flex gap-2 overflow-x-auto px-3 py-2 border-b border-edge-subtle">
      {attachments.map((attachment) => (
        <div
          key={attachment.id}
          className="relative group shrink-0"
        >
          <div className="h-16 w-16 overflow-hidden rounded-lg border-2 border-edge-subtle">
            <img
              src={attachment.previewUrl}
              alt="预览"
              className="h-full w-full object-cover"
            />
          </div>

          <button
            type="button"
            onClick={() => onRemove(attachment.id)}
            className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-surface-tertiary border border-edge text-content-muted opacity-0 group-hover:opacity-100 transition-opacity hover:bg-status-error hover:text-white hover:border-status-error"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
    </div>
  )
})
