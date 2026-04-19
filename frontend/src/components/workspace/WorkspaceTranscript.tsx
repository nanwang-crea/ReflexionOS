import type { RefObject } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2 } from 'lucide-react'
import { SlideIn } from '@/components/animations/SlideIn'
import { ActionReceipt } from '@/components/execution/ActionReceipt'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import type { Project } from '@/types/project'
import type { ChatSession, WorkspaceChatItem } from '@/types/workspace'

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

interface WorkspaceTranscriptProps {
  loaded: boolean
  configured: boolean
  currentProject: Project | null
  currentSession: ChatSession | null
  items: WorkspaceChatItem[]
  messagesEndRef: RefObject<HTMLDivElement>
}

export function WorkspaceTranscript({
  loaded,
  configured,
  currentProject,
  currentSession,
  items,
  messagesEndRef,
}: WorkspaceTranscriptProps) {
  return (
    <div className="flex-1 overflow-y-auto bg-white">
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

        {currentProject && !currentSession && items.length === 0 && (
          <div className="max-w-[720px] rounded-3xl border border-slate-200 bg-slate-50 px-6 py-8 text-slate-500">
            这个项目下还没有聊天。可以直接在下方输入，或者从左侧点击“新建聊天”。
          </div>
        )}

        <AnimatePresence mode="popLayout">
          {items.map((item) => {
            if (item.type === 'user-message') {
              return (
                <SlideIn key={item.id} direction="up">
                  <div className="mb-8 flex justify-end">
                    <motion.div
                      className="max-w-[720px] rounded-2xl bg-slate-100 px-5 py-4 text-[15px] leading-7 text-slate-700"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      {item.content}
                    </motion.div>
                  </div>
                </SlideIn>
              )
            }

            if (item.type === 'assistant-status') {
              return (
                <SlideIn key={item.id} direction="up">
                  <div className="mb-7 flex">
                    <div className="inline-flex items-center gap-2 rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-500">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{item.statusLabel}</span>
                    </div>
                  </div>
                </SlideIn>
              )
            }

            if (item.type === 'agent-update') {
              return (
                <SlideIn key={item.id} direction="up">
                  <div className="mb-7">
                    <MarkdownRenderer
                      content={item.content || ''}
                      variant="plain"
                      isStreaming={item.isStreaming}
                      className={transcriptClassName}
                    />
                  </div>
                </SlideIn>
              )
            }

            if (item.type === 'action-receipt') {
              return (
                <SlideIn key={item.id} direction="up">
                  <ActionReceipt
                    status={item.receiptStatus || 'running'}
                    details={item.details || []}
                  />
                </SlideIn>
              )
            }

            if (item.type === 'assistant-message') {
              return (
                <SlideIn key={item.id} direction="up">
                  <div className="mb-10">
                    <MarkdownRenderer
                      content={item.content || ''}
                      variant="plain"
                      isStreaming={item.isStreaming}
                      className={transcriptClassName}
                    />
                  </div>
                </SlideIn>
              )
            }

            return null
          })}
        </AnimatePresence>

        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
