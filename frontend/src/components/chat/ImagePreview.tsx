import { memo } from 'react'
import { Loader2, RotateCcw, X } from 'lucide-react'
import type { PendingAttachment } from '@/features/conversation/hooks/useImageUpload'

interface ImagePreviewProps {
  attachments: PendingAttachment[]
  onRemove: (id: string) => void
  onRetry: (id: string) => void
}

export const ImagePreview = memo(function ImagePreview({
  attachments,
  onRemove,
  onRetry,
}: ImagePreviewProps) {
  if (attachments.length === 0) return null

  return (
    <div className="flex gap-2 overflow-x-auto px-3 py-2 border-b border-edge-subtle">
      {attachments.map((attachment) => (
        <div
          key={attachment.id}
          className="relative group shrink-0"
        >
          <div
            className={`h-16 w-16 overflow-hidden rounded-lg border-2 ${
              attachment.status === 'error'
                ? 'border-status-error'
                : 'border-edge-subtle'
            }`}
          >
            <img
              src={attachment.previewUrl}
              alt="预览"
              className="h-full w-full object-cover"
            />

            {(attachment.status === 'compressing' || attachment.status === 'uploading') && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                <Loader2 className="h-5 w-5 animate-spin text-white" />
              </div>
            )}

            {attachment.status === 'error' && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                <button
                  type="button"
                  onClick={() => onRetry(attachment.id)}
                  className="rounded-full bg-white/20 p-1 hover:bg-white/40 transition-colors"
                  title="重试上传"
                >
                  <RotateCcw className="h-3 w-3 text-white" />
                </button>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => onRemove(attachment.id)}
            className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-surface-tertiary border border-edge text-content-muted opacity-0 group-hover:opacity-100 transition-opacity hover:bg-status-error hover:text-white hover:border-status-error"
          >
            <X className="h-3 w-3" />
          </button>

          {attachment.error && (
            <div className="absolute left-1/2 top-full z-10 mt-1 w-max max-w-[200px] -translate-x-1/2 rounded-md bg-status-error-soft px-2 py-1 text-xs text-status-error opacity-0 group-hover:opacity-100 transition-opacity">
              {attachment.error}
            </div>
          )}
        </div>
      ))}
    </div>
  )
})
