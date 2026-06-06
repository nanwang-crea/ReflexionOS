import { useState, useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronRight, Layers } from 'lucide-react'
import { ThinkingBlock } from './ThinkingBlock'
import { WorkingNoteBlock } from './WorkingNoteBlock'
import { ToolGroupItem } from './ToolGroupItem'
import type { ProcessSubItem } from './transcriptItems'
import type { ReceiptDetailClickHandler, ToolApprovalActionHandler } from './ToolTraceCard'

interface ProcessGroupBlockProps {
  runId: string
  subItems: ProcessSubItem[]
  isStreaming: boolean
  defaultExpanded: boolean
  autoCollapse: boolean
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: ReceiptDetailClickHandler
}

const COLLAPSED_BAR_LABEL = '展开过程'

export function ProcessGroupBlock({
  runId,
  subItems,
  isStreaming,
  defaultExpanded,
  autoCollapse,
  onApprovalAction,
  onDetailClick,
}: ProcessGroupBlockProps) {
  const storageKey = `process-collapsed-${runId}`

  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem(storageKey)
    if (stored !== null) return stored === 'true'
    if (autoCollapse && !isStreaming) return true
    return false
  })

  useEffect(() => {
    if (isStreaming && isCollapsed) {
      setIsCollapsed(false)
    }
  }, [isStreaming, isCollapsed])

  const autoCollapsedRef = useRef(false)
  useEffect(() => {
    if (isStreaming) {
      autoCollapsedRef.current = false
      return
    }
    if (autoCollapse && !autoCollapsedRef.current) {
      setIsCollapsed(true)
      autoCollapsedRef.current = true
    }
  }, [isStreaming, autoCollapse])

  useEffect(() => {
    localStorage.setItem(storageKey, String(isCollapsed))
  }, [storageKey, isCollapsed])

  return (
    <div className="mb-6 max-w-[920px] mx-auto w-full">
      <AnimatePresence mode="wait" initial={false}>
        {isCollapsed ? (
          <motion.button
            key="collapsed-bar"
            type="button"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setIsCollapsed(false)}
            className="flex w-full items-center gap-2 rounded-lg border border-edge bg-surface-secondary/40 px-3 py-2 text-sm text-content-muted transition-colors hover:bg-surface-secondary/70 hover:text-content-secondary"
            aria-expanded={false}
          >
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
            <Layers className="h-3.5 w-3.5 shrink-0" />
            <span>{COLLAPSED_BAR_LABEL}</span>
          </motion.button>
        ) : (
          <motion.div
            key="expanded-content"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {subItems.map((item) => {
              if (item.kind === 'thinking') {
                return (
                  <ThinkingBlock
                    key={item.id}
                    text={item.text}
                    isStreaming={item.streamState === 'streaming' || item.streamState === 'idle'}
                    defaultExpanded={defaultExpanded}
                  />
                )
              }
              if (item.kind === 'working_note') {
                return (
                  <WorkingNoteBlock
                    key={item.id}
                    text={item.text}
                    defaultExpanded={defaultExpanded}
                  />
                )
              }
              if (item.kind === 'tool_group') {
                return (
                  <ToolGroupItem
                    key={item.id}
                    status={item.status}
                    details={item.details}
                    onApprovalAction={onApprovalAction}
                    onDetailClick={onDetailClick}
                  />
                )
              }
              return null
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
