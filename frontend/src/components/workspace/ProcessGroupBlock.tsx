/**
 * 文件功能：过程分组展示区块
 * 文件描述：将一次 run 中的思考（thinking）、工作笔记（working_note）、工具调用组（tool_group）
 *          等中间过程项聚合展示，支持展开/收起，并将收起状态持久化到 localStorage
 * 核心逻辑：收起状态优先读取 localStorage 记忆值，否则按 autoCollapse && !isRunActive 决定初始状态；
 *          流式进行中若处于收起态会自动展开；run 结束后若开启 autoCollapse 则自动收起一次（用 ref 防重复触发）
 */
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

/**
 * 组件名：CollapseBar
 * 入参（props）：
 *   - onClick (() => void): 点击收起按钮时的回调
 * 作用/渲染逻辑：展开态下展示的“收起过程”操作条
 * 返回值：JSX.Element - 收起操作条
 */
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

/**
 * 组件名：ProcessGroupBlock
 * 入参（props，ProcessGroupBlockProps）：
 *   - runId (string): 所属 run 的 ID，用于生成 localStorage 存储键
 *   - subItems (ProcessSubItem[]): 过程子项列表（思考/工作笔记/工具调用组）
 *   - isStreaming (boolean): 该 run 是否仍在流式输出中
 *   - isRunActive (boolean): 该 run 是否仍处于活跃（未结束）状态
 *   - defaultExpanded (boolean): 子项（思考/工作笔记块）默认是否展开
 *   - autoCollapse (boolean): run 结束后是否自动收起整个过程区块
 *   - onApprovalAction (ToolApprovalActionHandler，可选): 审批操作回调，转发给工具调用组
 *   - onDetailClick (ReceiptDetailClickHandler，可选): 详情点击回调，转发给工具调用组
 * 作用/渲染逻辑：
 *   1. 初始收起状态：优先取 localStorage 记忆值，否则按 autoCollapse && !isRunActive 计算
 *   2. 流式输出中若处于收起态自动展开；run 由活跃变为非活跃且开启 autoCollapse 时自动收起一次
 *   3. 收起状态变化时持久化到 localStorage
 *   4. 收起态渲染展开入口条；展开态渲染收起条 + 按 kind 分发渲染 ThinkingBlock/WorkingNoteBlock/ToolGroupItem
 * 返回值：JSX.Element - 过程分组展示区块（收起条或展开内容）
 */
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
