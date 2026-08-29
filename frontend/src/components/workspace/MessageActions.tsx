/**
 * 文件功能：消息操作按钮组
 * 文件描述：展示消息下方的悬浮操作按钮（复制/编辑/重新生成），按消息类型区分显示编辑或重新生成按钮
 * 核心逻辑：复制操作调用 clipboard API 并通过 toast 提示结果，2 秒后恢复按钮提示文案
 */
import { useState } from 'react'
import { Copy, Pencil, RefreshCw } from 'lucide-react'
import { useToastStore } from '@/shared/stores/toast.store'

interface MessageActionsProps {
  messageId: string
  contentText: string
  messageType: 'user_message' | 'assistant_message'
  onEdit: (messageId: string, contentText: string) => void
  onRegenerate: (messageId: string) => void
}

/**
 * 组件名：MessageActions
 * 入参（props）：
 *   - messageId (string): 消息唯一标识
 *   - contentText (string): 消息文本内容（用于复制/编辑/重新生成）
 *   - messageType ('user_message' | 'assistant_message'): 消息类型，决定展示编辑按钮还是重新生成按钮
 *   - onEdit ((messageId, contentText) => void): 点击编辑按钮时的回调（仅用户消息展示）
 *   - onRegenerate ((messageId) => void): 点击重新生成按钮时的回调（仅助手消息展示）
 * 作用/渲染逻辑：
 *   1. 始终展示复制按钮：复制成功/失败均通过 toast 提示，复制成功后短暂切换提示文案为“已复制”
 *   2. 用户消息展示编辑按钮，助手消息展示重新生成按钮
 * 返回值：JSX.Element - 操作按钮组
 */
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
    <div className="mt-1 flex w-full max-w-[920px] gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
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
