import { useState, useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, ChevronRight, Layers } from 'lucide-react'
import { ThinkingBlock } from './ThinkingBlock'
import { WorkingNoteBlock } from './WorkingNoteBlock'
import { ToolGroupItem } from './ToolGroupItem'
import type { ProcessSubItem } from './transcriptItems'
import type { ReceiptDetailClickHandler, ToolApprovalActionHandler } from './ToolTraceCard'

interface ProcessGroupBlockProps {
  runId: string
  subItems: ProcessSubItem[]
  isStreaming: boolean
  isRunActive: boolean
  defaultExpanded: boolean
  autoCollapse: boolean
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: ReceiptDetailClickHandler
}

const EXPAND_LABEL = '展开过程'
const COLLAPSE_LABEL = '收起过程'

function CollapseBar({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-lg border border-edge bg-surface-secondary/40 px-3 py-2 text-sm text-content-muted transition-colors hover:bg-surface-secondary/70 hover:text-content-secondary"
      aria-expanded={false}
    >
      <ChevronDown className="h-3.5 w-3.5 shrink-0" />
      <Layers className="h-3.5 w-3.5 shrink-0" />
      <span>{COLLAPSE_LABEL}</span>
    </button>
  )
}

export function ProcessGroupBlock({
  runId,
  subItems,
  isStreaming,
  isRunActive,
  defaultExpanded,
  autoCollapse,
  onApprovalAction,
  onDetailClick,
}: ProcessGroupBlockProps) {
  const storageKey = `process-collapsed-${runId}`

  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem(storageKey)
    if (stored !== null) return stored === 'true'
    if (autoCollapse && !isRunActive) return true
    return false
  })

  useEffect(() => {
    if (isStreaming && isCollapsed) {
      setIsCollapsed(false)
    }
  }, [isStreaming, isCollapsed])

  const autoCollapsedRef = useRef(false)
  useEffect(() => {
    if (isRunActive) {
      autoCollapsedRef.current = false
      return
    }
    if (autoCollapse && !autoCollapsedRef.current) {
      setIsCollapsed(true)
      autoCollapsedRef.current = true
    }
  }, [isRunActive, autoCollapse])

  useEffect(() => {
    localStorage.setItem(storageKey, String(isCollapsed))
  }, [storageKey, isCollapsed])

  if (isCollapsed) {
    return (
      <div className="mb-6 max-w-[920px] mx-auto w-full">
        <motion.button
          key="collapsed-bar"
          type="button"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
          onClick={() => setIsCollapsed(false)}
          className="flex w-full items-center gap-2 rounded-lg border border-edge bg-surface-secondary/40 px-3 py-2 text-sm text-content-muted transition-colors hover:bg-surface-secondary/70 hover:text-content-secondary"
          aria-expanded={false}
        >
          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          <Layers className="h-3.5 w-3.5 shrink-0" />
          <span>{EXPAND_LABEL}</span>
        </motion.button>
      </div>
    )
  }

  return (
    <div className="mb-6 max-w-[920px] mx-auto w-full">
      <AnimatePresence initial={false}>
        <motion.div
          key="expanded-content"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
        >
          <CollapseBar onClick={() => setIsCollapsed(true)} />
          <div className="my-2">
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
          </div>
          <CollapseBar onClick={() => setIsCollapsed(true)} />
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
