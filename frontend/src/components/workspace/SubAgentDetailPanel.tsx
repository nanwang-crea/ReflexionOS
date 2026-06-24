/**
 * SubAgentDetailPanel — 子 Agent 实时执行详情的二级对话页面。
 *
 * 以全屏 overlay 形式覆盖在主对话上方，展示子 agent 的实时执行步骤流。
 * 点击返回按钮或按 Escape 关闭，回到主对话。
 *
 * 渲染逻辑复用主聊天页面的组件：
 * - ThinkingBlock 用于 llm:reasoning（思考过程）
 * - MarkdownRenderer 用于 llm:content（模型输出）
 * - ActionReceipt + buildReceiptDetail 用于 tool:start/tool:result 工具调用
 */
import { memo, useCallback, useEffect, useMemo, useRef } from 'react'
import { Loader2, ArrowLeft } from 'lucide-react'
import type { SubAgentStep } from '@/hooks/useSubAgentEvents'
import { ThinkingBlock } from './ThinkingBlock'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { ActionReceipt } from '@/components/execution/ActionReceipt'
import { buildReceiptDetail } from '@/components/execution/receiptUtils'
import type { ActionReceiptDetail, ActionReceiptStatus } from '@/components/execution/receiptUtils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SubAgentDetailPanelProps {
  /** 子 agent 任务描述 */
  task: string
  /** 实时步骤列表 */
  steps: SubAgentStep[]
  /** 是否仍在运行 */
  isRunning: boolean
  /** 关闭面板回到主对话 */
  onClose: () => void
}

/** 渲染项：将原始步骤分组为可渲染的结构 */
type SubAgentRenderItem =
  | { kind: 'thinking'; text: string; isStreaming: boolean; key: string }
  | { kind: 'content'; text: string; key: string }
  | { kind: 'tool_group'; details: ActionReceiptDetail[]; status: ActionReceiptStatus; key: string }
  | { kind: 'delegate'; label: string; taskText: string; key: string }
  | { kind: 'error'; text: string; key: string }

// ---------------------------------------------------------------------------
// buildSubAgentRenderItems — 将 SubAgentStep[] 分组为渲染项
// ---------------------------------------------------------------------------

/**
 * 将子 agent 的原始事件步骤转换为分组渲染项。
 *
 * 分组规则（与主聊天页面 buildTranscriptItems 一致）：
 * 1. 连续的 llm:reasoning 合并为一个 thinking 项
 * 2. 连续的 llm:content 合并为一个 content 项（用 MarkdownRenderer 渲染）
 * 3. tool:start + tool:result/error 配对为 tool_group（用 ActionReceipt 渲染）
 * 4. delegate:start/result/error 为委托项
 * 5. 遇到不同类型的事件时，先刷新当前缓冲区
 */
function buildSubAgentRenderItems(steps: SubAgentStep[]): SubAgentRenderItem[] {
  const items: SubAgentRenderItem[] = []

  // 当前缓冲区：用于合并连续的同类事件
  let thinkingBuf = ''
  let contentBuf = ''
  let thinkingStartIdx = 0
  let contentStartIdx = 0

  // 工具调用组：收集 tool:start 创建的 receipt detail，等待配对的 tool:result
  const toolGroup: ActionReceiptDetail[] = []
  let toolStartStepIdx = 0

  /** 刷新 thinking 缓冲区 */
  const flushThinking = (isLast: boolean) => {
    if (thinkingBuf) {
      items.push({
        kind: 'thinking',
        text: thinkingBuf,
        // 最后一批且仍在运行 → 流式状态
        isStreaming: isLast,
        key: `thinking-${thinkingStartIdx}`,
      })
      thinkingBuf = ''
    }
  }

  /** 刷新 content 缓冲区 */
  const flushContent = () => {
    if (contentBuf) {
      items.push({ kind: 'content', text: contentBuf, key: `content-${contentStartIdx}` })
      contentBuf = ''
    }
  }

  /** 刷新工具组 */
  const flushToolGroup = () => {
    if (toolGroup.length > 0) {
      // 判断整体状态
      const allDone = toolGroup.every(d =>
        d.status === 'success' || d.status === 'failed' || d.status === 'cancelled'
      )
      const anyFailed = toolGroup.some(d => d.status === 'failed')
      const status: ActionReceiptStatus = allDone
        ? (anyFailed ? 'partial_failed' : 'completed')
        : 'running'
      items.push({
        kind: 'tool_group',
        details: [...toolGroup],
        status,
        key: `tools-${toolStartStepIdx}`,
      })
      toolGroup.length = 0
    }
  }

  /** 刷新所有缓冲区（遇到不同类型的事件时调用） */
  const flushAll = (isLast = false) => {
    flushThinking(isLast)
    flushContent()
    flushToolGroup()
  }

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i]
    const { eventType, payload } = step

    switch (eventType) {
      case 'llm:reasoning': {
        // 先刷新其他类型的缓冲区
        flushContent()
        flushToolGroup()
        // 合并连续的 reasoning 块
        if (!thinkingBuf) thinkingStartIdx = i
        thinkingBuf += typeof payload.reasoning_content === 'string' ? payload.reasoning_content : ''
        break
      }

      case 'llm:content': {
        flushThinking(false)
        flushToolGroup()
        if (!contentBuf) contentStartIdx = i
        contentBuf += typeof payload.content === 'string' ? payload.content : ''
        break
      }

      case 'tool:start': {
        flushAll()
        // 使用 buildReceiptDetail 构造标准的 receipt detail
        const toolName = typeof payload.tool_name === 'string' ? payload.tool_name : 'unknown'
        const toolCallId = typeof payload.tool_call_id === 'string' ? payload.tool_call_id : `tc_${i}`
        const args = (payload.arguments as Record<string, unknown>) ?? {}
        const detail = buildReceiptDetail(toolCallId, toolName, args)
        // tool:start 意味着工具已在执行
        detail.status = 'running'
        toolGroup.push(detail)
        if (toolGroup.length === 1) toolStartStepIdx = i
        break
      }

      case 'tool:result': {
        flushThinking(false)
        flushContent()
        // 找到配对的 tool:start 并更新状态
        const resultCallId = typeof payload.tool_call_id === 'string' ? payload.tool_call_id : undefined
        const matched = resultCallId
          ? toolGroup.find(d => d.id === resultCallId)
          : toolGroup.find(d => d.status === 'running')
        if (matched) {
          matched.status = payload.success !== false ? 'success' : 'failed'
          matched.output = typeof payload.result === 'string' ? payload.result : undefined
          if (typeof payload.duration === 'number') {
            matched.duration = payload.duration
          }
        }
        break
      }

      case 'tool:error': {
        flushThinking(false)
        flushContent()
        const errorCallId = typeof payload.tool_call_id === 'string' ? payload.tool_call_id : undefined
        const matchedErr = errorCallId
          ? toolGroup.find(d => d.id === errorCallId)
          : toolGroup.find(d => d.status === 'running')
        if (matchedErr) {
          matchedErr.status = 'failed'
          matchedErr.error = typeof payload.error === 'string' ? payload.error : undefined
        }
        break
      }

      case 'delegate:start':
      case 'delegate:call': {
        flushAll()
        const taskStr = typeof payload.task === 'string' ? payload.task : ''
        const label = typeof payload.tool_name === 'string' ? payload.tool_name : 'delegate'
        items.push({
          kind: 'delegate',
          label,
          taskText: taskStr,
          key: `delegate-${i}`,
        })
        break
      }

      case 'delegate:result': {
        flushAll()
        const resultText = typeof payload.result === 'string' ? payload.result : undefined
        if (resultText) {
          items.push({ kind: 'content', text: resultText, key: `delegate-result-${i}` })
        }
        break
      }

      case 'delegate:error': {
        flushAll()
        const errText = typeof payload.error === 'string' ? payload.error : '委托执行失败'
        items.push({ kind: 'error', text: errText, key: `delegate-error-${i}` })
        break
      }

      default: {
        // 未知事件类型，刷新缓冲区
        flushAll()
        break
      }
    }
  }

  // 最终刷新 — 最后一批 thinking 如果仍在运行则标记 isStreaming
  flushAll(true)

  return items
}

// ---------------------------------------------------------------------------
// RenderItem — 单个渲染项
// ---------------------------------------------------------------------------

const RenderItem = memo(function RenderItem({ item }: { item: SubAgentRenderItem }) {
  switch (item.kind) {
    case 'thinking':
      return (
        <div className="px-4 py-2">
          <ThinkingBlock text={item.text} isStreaming={item.isStreaming} />
        </div>
      )

    case 'content':
      return (
        <div className="px-4 py-2 text-sm leading-6 text-content-primary [&>div]:max-w-none">
          <MarkdownRenderer content={item.text} />
        </div>
      )

    case 'tool_group':
      return (
        <div className="px-4 py-2">
          <ActionReceipt details={item.details} status={item.status} />
        </div>
      )

    case 'delegate':
      return (
        <div className="px-4 py-2">
          <div className="inline-flex items-center gap-1.5 text-xs font-mono text-content-secondary bg-surface-tertiary rounded px-2 py-1">
            <Loader2 className="h-3 w-3 animate-spin text-accent" />
            <span>{item.label}</span>
            {item.taskText && (
              <span className="text-content-muted truncate max-w-[400px]">
                {item.taskText.slice(0, 100)}
              </span>
            )}
          </div>
        </div>
      )

    case 'error':
      return (
        <div className="px-4 py-2">
          <div className="text-sm text-red-500 bg-red-500/10 rounded-lg px-3 py-2">
            {item.text}
          </div>
        </div>
      )
  }
})

// ---------------------------------------------------------------------------
// SubAgentDetailPanel
// ---------------------------------------------------------------------------

/**
 * 子 Agent 实时执行详情面板（二级对话页面）
 *
 * 全屏 overlay，展示子 agent 的实时步骤流，支持 Escape 或点击返回关闭。
 */
export function SubAgentDetailPanel({
  task,
  steps,
  isRunning,
  onClose,
}: SubAgentDetailPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const prevLenRef = useRef(0)

  // 将原始步骤分组为渲染项
  const renderItems = useMemo(() => buildSubAgentRenderItems(steps), [steps])

  // 新步骤到达时自动滚动到底部
  useEffect(() => {
    if (steps.length !== prevLenRef.current) {
      prevLenRef.current = steps.length
      const el = scrollRef.current
      if (el) {
        requestAnimationFrame(() => {
          el.scrollTop = el.scrollHeight
        })
      }
    }
  }, [steps.length])

  // Escape 关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleClose = useCallback(() => onClose(), [onClose])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-surface-primary">
      {/* 顶部导航栏 */}
      <div className="flex items-center gap-3 border-b border-edge px-4 py-3 shrink-0">
        <button
          type="button"
          onClick={handleClose}
          className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-content-secondary hover:bg-surface-tertiary hover:text-content-primary transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>返回</span>
        </button>

        <div className="h-4 w-px bg-edge" />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />}
            <span className="text-sm font-medium text-content-primary truncate">
              {isRunning ? '子 Agent 执行中' : '子 Agent 执行完成'}
            </span>
            <span className="text-xs text-content-muted">
              {steps.length} 步
            </span>
          </div>
          <p className="text-xs text-content-muted mt-0.5 truncate">{task}</p>
        </div>
      </div>

      {/* 渲染项列表 — 复用主聊天页面的组件 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto"
      >
        {renderItems.length === 0 && isRunning && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-content-muted">
            <Loader2 className="h-8 w-8 animate-spin text-accent" />
            <p className="text-sm">子 Agent 正在启动...</p>
          </div>
        )}

        {renderItems.length === 0 && !isRunning && (
          <div className="flex items-center justify-center h-full text-content-muted text-sm">
            暂无执行记录
          </div>
        )}

        {renderItems.length > 0 && (
          <div className="max-w-[920px] mx-auto w-full py-2">
            {renderItems.map((item) => (
              <RenderItem key={item.key} item={item} />
            ))}

            {/* 运行中的尾部指示器 */}
            {isRunning && (
              <div className="flex items-center gap-2 px-4 py-3 text-content-muted">
                <Loader2 className="h-4 w-4 animate-spin text-accent" />
                <span className="text-xs">等待下一步...</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
