import { useEffect, useState } from 'react'
import type { RefObject, UIEventHandler } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { SlideIn } from '@/components/animations/SlideIn'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { ToolTraceCard } from '@/components/workspace/ToolTraceCard'
import type { Project } from '@/types/project'
import type { ConversationMessage } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'
import type { Plan } from '@/types/conversation'
import type { SessionSummary } from '@/types/workspace'
import { Loader2 } from 'lucide-react'
import { PlanProgress } from './PlanProgress'

const transcriptClassName = [
  'max-w-[920px]',
  'text-[17px]',
  'leading-[1.8]',
  'text-slate-900',
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
  transcriptScrollRef?: RefObject<HTMLDivElement>
  onTranscriptScroll?: UIEventHandler<HTMLDivElement>
  messagesEndRef: RefObject<HTMLDivElement>
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
  transcriptScrollRef,
  onTranscriptScroll,
  messagesEndRef,
}: WorkspaceTranscriptProps) {
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
      className="flex-1 overflow-y-auto bg-white"
    >
      <div className="mx-auto w-full max-w-[1280px] px-8 py-8">
        {loaded && !configured && (
          <div className="mb-4 rounded-lg border border-yellow-200 bg-yellow-50 p-4">
            <p className="text-yellow-800">请先在设置页面配置供应商、模型和默认项</p>
          </div>
        )}

        {!currentProject && (
          <div className="max-w-[720px] rounded-3xl border border-slate-200 bg-slate-50 px-6 py-8 text-slate-500">
            先在左侧选择一个项目，再开始新的聊天。
          </div>
        )}

        {currentProject && !currentSession && messages.length === 0 && (
          <div className="max-w-[720px] rounded-3xl border border-slate-200 bg-slate-50 px-6 py-8 text-slate-500">
            这个项目下还没有聊天。可以直接在下方输入，或者从左侧点击“新建聊天”。
          </div>
        )}

        <AnimatePresence mode="popLayout">
          {messages.map((message) => {
            if (message.messageType === 'user_message') {
              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-8 flex justify-end">
                    <motion.div
                      className="max-w-[720px] rounded-2xl bg-slate-100 px-5 py-4 text-[15px] leading-7 text-slate-700"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      {message.contentText}
                    </motion.div>
                  </div>
                </SlideIn>
              )
            }

            if (message.messageType === 'tool_trace') {
              return (
                <SlideIn key={message.id} direction="up">
                  <ToolTraceCard message={message} />
                </SlideIn>
              )
            }

            if (message.messageType === 'system_notice') {
              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-6 max-w-[920px] rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    {message.contentText}
                  </div>
                </SlideIn>
              )
            }

            if (message.messageType === 'assistant_message') {
              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-10">
                    <MarkdownRenderer
                      content={message.contentText || ''}
                      variant="plain"
                      isStreaming={message.streamState === 'streaming'}
                      className={transcriptClassName}
                    />
                  </div>
                </SlideIn>
              )
            }

            return null
          })}
        </AnimatePresence>

        {showReconnectIndicator && (
          <div className="mb-8 flex items-center gap-3 text-sm text-amber-600" aria-live="polite">
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-500" />
            <span>{reconnectLabel} · {reconnectCountdownSeconds} 秒后重试</span>
          </div>
        )}

        {showThinkingIndicator && (
          <div className="mb-8 flex items-center gap-3 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
            <span>思考中</span>
          </div>
        )}

        <AnimatePresence>
          {plan && <PlanProgress plan={plan} />}
        </AnimatePresence>

        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
