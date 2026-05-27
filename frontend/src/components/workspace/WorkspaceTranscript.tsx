import { useEffect, useMemo, useState } from 'react'
import type { RefObject, UIEventHandler } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SlideIn } from '@/components/animations/SlideIn'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { ToolTraceGroup } from '@/components/workspace/ToolTraceCard'
import type { ToolApprovalActionHandler } from '@/components/workspace/ToolTraceCard'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
import type { Project } from '@/types/project'
import type { ConversationMessage, ConversationRun } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'
import type { Plan } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import { ArrowDown, Loader2 } from 'lucide-react'
import { MessageActions } from './MessageActions'
import { PlanProgress } from './PlanProgress'
import { buildTranscriptItems } from './transcriptItems'

const transcriptClassName = [
  'max-w-[920px]',
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

export function getRetryCountdownSeconds(delay: number, elapsedMs = 0) {
  const delaySeconds = Number.isFinite(delay) ? Math.max(0, Math.ceil(delay)) : 0
  const elapsedSeconds = Math.max(0, Math.floor(elapsedMs / 1000))
  return Math.max(0, delaySeconds - elapsedSeconds)
}

interface WorkspaceTranscriptProps {
  loaded: boolean
  configured: boolean
  currentProject: Project | null
  currentSession: SessionSummary | null
  messages: ConversationMessage[]
  isRunning?: boolean
  retryInfo?: LlmRetryDto | null
  plan?: Plan | null
  isPlanMinimized?: boolean
  onTogglePlanMinimize?: () => void
  transcriptScrollRef?: RefObject<HTMLDivElement>
  onTranscriptScroll?: UIEventHandler<HTMLDivElement>
  isAtBottom?: boolean
  onScrollToBottom?: () => void
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: (detail: ActionReceiptDetail) => void
  messagesEndRef: RefObject<HTMLDivElement>
  runsById?: Record<string, ConversationRun>
  onEditMessage?: (messageId: string, contentText: string) => void
  onRegenerateMessage?: (messageId: string) => void
}

export function WorkspaceTranscript({
  loaded,
  configured,
  currentProject,
  currentSession,
  messages,
  isRunning = false,
  retryInfo = null,
  plan = null,
  isPlanMinimized = false,
  onTogglePlanMinimize,
  transcriptScrollRef,
  onTranscriptScroll,
  isAtBottom = true,
  onScrollToBottom,
  onApprovalAction,
  onDetailClick,
  messagesEndRef,
  runsById,
  onEditMessage,
  onRegenerateMessage,
}: WorkspaceTranscriptProps) {
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const transcriptItems = useMemo(() => buildTranscriptItems(messages), [messages])
  const hasVisibleStreamingMessage = messages.some((message) => {
    if (message.messageType === 'assistant_message' && message.streamState === 'streaming') {
      return true
    }
    if (message.messageType === 'tool_trace' && (message.streamState === 'streaming' || message.streamState === 'idle')) {
      return true
    }
    return false
  })

  const [reconnectCountdownSeconds, setReconnectCountdownSeconds] = useState(() => (
    getRetryCountdownSeconds(retryInfo?.delay ?? 0)
  ))
  const hasRetryInfo = retryInfo !== null
  const retryAttempt = retryInfo?.attempt ?? null
  const retryDelay = retryInfo?.delay ?? 0
  const retryMaxRetries = retryInfo?.max_retries ?? null
  const reconnectLabel = hasRetryInfo ? `reconnect（${retryAttempt}/${retryMaxRetries}）` : null
  const showReconnectIndicator = isRunning && reconnectLabel !== null
  const showThinkingIndicator = isRunning && !showReconnectIndicator && !hasVisibleStreamingMessage && !plan

  useEffect(() => {
    if (!hasRetryInfo || !isRunning) {
      setReconnectCountdownSeconds(0)
      return
    }

    setReconnectCountdownSeconds(getRetryCountdownSeconds(retryDelay))
    const intervalId = window.setInterval(() => {
      setReconnectCountdownSeconds((seconds) => Math.max(0, seconds - 1))
    }, 1000)

    return () => window.clearInterval(intervalId)
  }, [hasRetryInfo, isRunning, retryAttempt, retryDelay, retryMaxRetries])

  return (
    <div
      ref={transcriptScrollRef}
      onScroll={onTranscriptScroll}
      className="flex-1 overflow-y-auto bg-surface-primary"
    >
      <div className="mx-auto w-full max-w-[1280px] px-8 py-8">
        {loaded && !configured && (
          <div className="mb-4 rounded-lg border border-status-warning-border bg-status-warning-soft p-4">
            <p className="text-status-warning">请先在设置页面配置供应商、模型和默认项</p>
          </div>
        )}

        {!currentProject && (
          <div className="max-w-[720px] rounded-3xl border border-edge bg-surface-secondary px-6 py-8 text-content-muted">
            先在左侧选择一个项目，再开始新的聊天。
          </div>
        )}

        {currentProject && !currentSession && messages.length === 0 && (
          <div className="max-w-[720px] rounded-3xl border border-edge bg-surface-secondary px-6 py-8 text-content-muted">
            这个项目下还没有聊天。可以直接在下方输入，或者从左侧点击“新建聊天”。
          </div>
        )}

        <AnimatePresence mode="popLayout">
          {transcriptItems.map((item) => {
            if (item.kind === 'tool_group') {
              return (
                <SlideIn key={item.id} direction="up">
                  <ToolTraceGroup
                    status={item.status}
                    details={item.details}
                    onApprovalAction={onApprovalAction}
                    onDetailClick={onDetailClick}
                  />
                </SlideIn>
              )
            }

            const { message } = item

            if (message.messageType === 'user_message') {
              const isEditing = editingMessageId === message.id
              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-8 flex flex-col items-end group">
                    {isEditing ? (
                      <div className="max-w-[720px] w-full">
                        <textarea
                          className="w-full rounded-2xl bg-surface-tertiary border border-edge px-5 py-4 text-[15px] leading-7 text-content-secondary resize-y min-h-[60px] focus:outline-none focus:border-edge-active"
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          autoFocus
                        />
                        <div className="mt-2 flex justify-end gap-2">
                          <button
                            type="button"
                            className="rounded-lg border border-edge px-3 py-1.5 text-xs text-content-muted hover:text-content-secondary hover:border-edge-active transition-colors"
                            onClick={() => setEditingMessageId(null)}
                          >
                            取消
                          </button>
                          <button
                            type="button"
                            className="rounded-lg bg-surface-tertiary px-3 py-1.5 text-xs text-content-secondary hover:bg-surface-active transition-colors"
                            onClick={() => {
                              if (editContent.trim()) {
                                onEditMessage?.(message.id, editContent.trim())
                                setEditingMessageId(null)
                              }
                            }}
                          >
                            发送
                          </button>
                        </div>
                      </div>
                    ) : (
                      <motion.div
                        className="max-w-[720px] rounded-2xl bg-surface-tertiary px-5 py-4 text-[15px] leading-7 text-content-secondary"
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        {message.contentText}
                      </motion.div>
                    )}
                    {!isEditing && onEditMessage && (
                      <MessageActions
                        messageId={message.id}
                        contentText={message.contentText}
                        messageType="user_message"
                        onEdit={(msgId, content) => {
                          setEditingMessageId(msgId)
                          setEditContent(content)
                        }}
                        onRegenerate={onRegenerateMessage ?? (() => {})}
                      />
                    )}
                  </div>
                </SlideIn>
              )
            }

            if (message.messageType === 'tool_trace') {
              return null
            }

            if (message.messageType === 'system_notice') {
              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-6 max-w-[920px] rounded-2xl border border-status-warning-border bg-status-warning-soft px-4 py-3 text-sm text-status-warning">
                    {message.contentText}
                  </div>
                </SlideIn>
              )
            }

            if (message.messageType === 'assistant_message') {
              const isFailed = message.streamState === 'failed'
              const isCancelled = message.streamState === 'cancelled'
              const run = message.runId != null ? runsById?.[message.runId] : undefined
              const errorCode = (message.payloadJson?.error_code as string | undefined) ?? run?.errorCode ?? undefined
              const errorMessage = (message.payloadJson?.error_message as string | undefined) ?? run?.errorMessage ?? undefined

              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-10 group">
                    {message.contentText && (
                      <MarkdownRenderer
                        content={message.contentText}
                        variant="plain"
                        isStreaming={message.streamState === 'streaming'}
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
                    {message.streamState === 'completed' && onRegenerateMessage && (
                      <MessageActions
                        messageId={message.id}
                        contentText={message.contentText}
                        messageType="assistant_message"
                        onEdit={onEditMessage ?? (() => {})}
                        onRegenerate={onRegenerateMessage}
                      />
                    )}
                  </div>
                </SlideIn>
              )
            }

            return null
          })}
        </AnimatePresence>

        {showReconnectIndicator && (
          <div className="mb-8 flex items-center gap-3 text-sm text-status-warning" aria-live="polite">
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-status-warning" />
            <span>{reconnectLabel} · {reconnectCountdownSeconds} 秒后重试</span>
          </div>
        )}

        {showThinkingIndicator && (
          <div className="mb-8 flex items-center gap-3 text-sm text-content-muted">
            <Loader2 className="h-4 w-4 animate-spin text-content-muted" />
            <span>思考中</span>
          </div>
        )}

        <AnimatePresence>
          {plan && (
            <PlanProgress
              plan={plan}
              isMinimized={isPlanMinimized}
              onToggleMinimize={onTogglePlanMinimize ?? (() => {})}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {!isAtBottom && onScrollToBottom && (
            <motion.button
              type="button"
              aria-label="滚动到底部"
              title="滚动到底部"
              onClick={onScrollToBottom}
              initial={{ opacity: 0, y: 10, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.96 }}
              transition={{ duration: 0.18 }}
              className="sticky bottom-4 z-20 mx-auto mb-4 grid h-11 w-11 place-items-center rounded-full border border-edge bg-surface-primary text-content-secondary shadow-theme transition-colors hover:border-edge hover:text-content-primary"
            >
              <ArrowDown className="h-5 w-5" />
            </motion.button>
          )}
        </AnimatePresence>

        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
