import { useState } from 'react'
import { Copy, Pencil, RefreshCw } from 'lucide-react'
import { useToastStore } from '@/stores/toastStore'

interface MessageActionsProps {
  messageId: string
  contentText: string
  messageType: 'user_message' | 'assistant_message'
  onEdit: (messageId: string, contentText: string) => void
  onRegenerate: (messageId: string) => void
}

export function MessageActions({
  messageId,
  contentText,
  messageType,
  onEdit,
  onRegenerate,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(contentText)
      setCopied(true)
      useToastStore.getState().addToast('info', '已复制到剪贴板', 2000)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      useToastStore.getState().addToast('error', '复制失败')
    }
  }

  const buttonBaseClass =
    'inline-flex items-center justify-center h-7 w-7 rounded-md transition-colors text-content-muted hover:bg-surface-tertiary hover:text-content-secondary'

  return (
    <div className="mt-1 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
      <button
        type="button"
        className={buttonBaseClass}
        title={copied ? '已复制' : '复制'}
        onClick={handleCopy}
      >
        <Copy className="h-4 w-4" />
      </button>
      {messageType === 'user_message' && (
        <button
          type="button"
          className={buttonBaseClass}
          title="编辑"
          onClick={() => onEdit(messageId, contentText)}
        >
          <Pencil className="h-4 w-4" />
        </button>
      )}
      {messageType === 'assistant_message' && (
        <button
          type="button"
          className={buttonBaseClass}
          title="重新生成"
          onClick={() => onRegenerate(messageId)}
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
