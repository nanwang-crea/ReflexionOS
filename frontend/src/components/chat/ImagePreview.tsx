import { memo } from 'react'
import { X } from 'lucide-react'
import type { PendingAttachment } from '@/features/conversation/hooks/useImageUpload'

interface ImagePreviewProps {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
}

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
