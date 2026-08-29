/**
 * 文件功能：助手消息展示组件
 * 文件描述：展示单条助手（AI）回复消息，支持 Markdown 渲染、流式输出态、失败/取消状态提示，
 *          以及完成后的操作按钮（复制/重新生成）
 * 核心逻辑：根据 streamState 判断失败/取消并展示对应错误提示（优先取 payload 中的错误信息，
 *          缺失时回退到所属 run 的错误信息）；仅在 completed 状态且提供了 onRegenerate 时展示操作按钮
 */
import { memo } from 'react'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { MessageActions } from './MessageActions'
import type { ConversationMessage, ConversationRun } from '@/types/conversation'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
import { useMessageContextMenu } from '@/hooks/useMessageContextMenu'

const transcriptClassName = [
  'max-w-[920px]',
  'mx-auto',
  'w-full',
  'text-[17px]',
  'leading-[1.8]',
  'text-content-primary',
  '[&_p]:m-0',
  '[&_p+p]:mt-6',
  '[&_ul]:my-4',
  '[&_ol]:my-4',
  '[&_li]:mt-1.5',
  '[&_h1]:mt-0',
  '[&_h2]:mt-8',
  '[&_h3]:mt-6',
  '[&_pre]:my-4',
  '[&_blockquote]:my-5',
].join(' ')

interface AssistantMessageItemProps {
  messageId: string
  contentText: string
  streamState: ConversationMessage['streamState']
  displayMode: string
  payloadJson: Record<string, unknown>
  runId: string | null
  runsById?: Record<string, ConversationRun>
  onEdit: (messageId: string, contentText: string) => void
  onRegenerate: (messageId: string) => void
  onDetailClick?: (detail: ActionReceiptDetail) => void
}

/**
 * 组件名：AssistantMessageItem
 * 入参（props，AssistantMessageItemProps）：
 *   - messageId (string): 消息唯一标识
 *   - contentText (string): 消息文本内容（Markdown 格式）
 *   - streamState (ConversationMessage['streamState']): 流式状态（streaming/completed/failed/cancelled 等）
 *   - displayMode (string): 展示模式（本组件未直接使用，由上层区分调用）
 *   - payloadJson (Record<string, unknown>): 原始 payload，可能携带 error_code/error_message
 *   - runId (string | null): 所属的 run ID，用于回退查找 run 级别的错误信息
 *   - runsById (Record<string, ConversationRun>，可选): run 信息映射表
 *   - onEdit ((messageId, contentText) => void): 编辑回调（转发给 MessageActions）
 *   - onRegenerate ((messageId) => void): 重新生成回调，仅 completed 状态下展示按钮
 *   - onDetailClick ((detail) => void，可选): 详情点击回调（本组件未直接使用）
 * 作用/渲染逻辑：
 *   1. 使用 MarkdownRenderer 渲染消息内容，流式中时开启流式渲染效果
 *   2. 失败/取消状态且存在错误信息时，展示对应样式的错误提示卡片
 *   3. completed 状态且提供了 onRegenerate 时，展示复制/重新生成操作按钮
 *   4. 支持右键菜单复制原始 Markdown 源码
 * 返回值：JSX.Element - 助手消息展示区块
 */
export const AssistantMessageItem = memo(function AssistantMessageItem({
  messageId,
  contentText,
  streamState,
  payloadJson,
  runId,
  runsById,
  onEdit,
  onRegenerate,
}: AssistantMessageItemProps) {
  const isFailed = streamState === 'failed'
  const isCancelled = streamState === 'cancelled'
  const run = runId != null ? runsById?.[runId] : undefined
  const errorCode = (typeof payloadJson?.error_code === 'string' ? payloadJson.error_code : undefined) ?? run?.errorCode ?? undefined
  const errorMessage = (typeof payloadJson?.error_message === 'string' ? payloadJson.error_message : undefined) ?? run?.errorMessage ?? undefined
  // 助手消息无选区时复制原始 Markdown 源码（即 contentText，MarkdownRenderer 的渲染输入）
  const handleContextMenu = useMessageContextMenu(() => contentText)

  return (
    <div className="mb-6 group" onContextMenu={handleContextMenu}>
      {contentText && (
        <MarkdownRenderer
          content={contentText}
          variant="plain"
          isStreaming={streamState === 'streaming'}
          className={transcriptClassName}
        />
      )}
      {(isFailed || isCancelled) && (errorMessage || errorCode) && (
        <div className={`mt-3 rounded-lg border px-4 py-3 text-sm ${
          isFailed
            ? 'border-status-error-border bg-status-error-soft text-status-error'
            : 'border-status-warning-border bg-status-warning-soft text-status-warning'
        }`}>
          <div className="flex items-center gap-2 font-medium">
            {isFailed ? '执行失败' : '执行已取消'}
          </div>
          {errorMessage && (
            <div className="mt-1 text-xs opacity-80">{errorMessage}</div>
          )}
        </div>
      )}
      {streamState === 'completed' && onRegenerate && (
        <MessageActions
          messageId={messageId}
          contentText={contentText}
          messageType="assistant_message"
          onEdit={onEdit}
          onRegenerate={onRegenerate}
        />
      )}
    </div>
  )
})
