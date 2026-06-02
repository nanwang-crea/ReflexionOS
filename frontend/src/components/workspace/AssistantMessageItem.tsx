import { memo } from 'react'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { MessageActions } from './MessageActions'
import { ThinkingBlock } from './ThinkingBlock'
import { WorkingNoteBlock } from './WorkingNoteBlock'
import type { ConversationMessage, ConversationRun } from '@/types/conversation'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
import { getAssistantReasoningText } from './runtimeStatus'

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

export const AssistantMessageItem = memo(function AssistantMessageItem({
  messageId,
  contentText,
  streamState,
  displayMode,
  payloadJson,
  runId,
  runsById,
  onEdit,
  onRegenerate,
}: AssistantMessageItemProps) {
  const isFailed = streamState === 'failed'
  const isCancelled = streamState === 'cancelled'
  const run = runId != null ? runsById?.[runId] : undefined
  const errorCode = (payloadJson?.error_code as string | undefined) ?? run?.errorCode ?? undefined
  const errorMessage = (payloadJson?.error_message as string | undefined) ?? run?.errorMessage ?? undefined
  const reasoningText = getAssistantReasoningText({
    contentText,
    streamState,
    displayMode,
    payloadJson,
    runId,
  } as ConversationMessage)
  const shouldCollapseThinking = streamState !== 'streaming'
  const isWorkingNote = displayMode === 'working_note'

  return (
    <div className="mb-6 group">
      {reasoningText && (
        <ThinkingBlock
          text={reasoningText}
          isStreaming={!shouldCollapseThinking}
        />
      )}
      {isWorkingNote && contentText && (
        <WorkingNoteBlock text={contentText} />
      )}
      {!isWorkingNote && contentText && (
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
