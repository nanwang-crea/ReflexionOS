/**
 * SubAgentDetailPanel — 子 Agent 实时执行详情的二级对话页面。
 *
 * 以全屏 overlay 形式覆盖在主对话上方，展示子 agent 的实时执行步骤流。
 * 点击返回按钮或按 Escape 关闭，回到主对话。
 */
import { useCallback, useEffect, useRef } from 'react'
import {
  Loader2,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Wrench,
  MessageSquare,
} from 'lucide-react'
import type { SubAgentStep } from '@/hooks/useSubAgentEvents'

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

/** 根据事件类型返回对应的图标和样式 */
function getStepVisual(step: SubAgentStep): {
  icon: React.ReactNode
  label: string
  colorClass: string
} {
  const t = step.eventType
  if (t === 'tool:start') {
    return {
      icon: <Wrench className="h-3.5 w-3.5" />,
      label: '工具调用',
      colorClass: 'text-accent',
    }
  }
  if (t === 'tool:result') {
    const success = step.payload.success !== false
    return {
      icon: success
        ? <CheckCircle2 className="h-3.5 w-3.5" />
        : <AlertCircle className="h-3.5 w-3.5" />,
      label: success ? '工具完成' : '工具失败',
      colorClass: success ? 'text-green-500' : 'text-red-500',
    }
  }
  if (t === 'tool:error') {
    return {
      icon: <AlertCircle className="h-3.5 w-3.5" />,
      label: '工具错误',
      colorClass: 'text-red-500',
    }
  }
  if (t === 'llm:content') {
    return {
      icon: <MessageSquare className="h-3.5 w-3.5" />,
      label: '模型输出',
      colorClass: 'text-content-secondary',
    }
  }
  return {
    icon: <Wrench className="h-3.5 w-3.5" />,
    label: t,
    colorClass: 'text-content-muted',
  }
}

/** 单条步骤的渲染 */
function StepItem({ step }: { step: SubAgentStep }) {
  const { icon, label, colorClass } = getStepVisual(step)
  const payload = step.payload

  const toolName = typeof payload.tool_name === 'string' ? payload.tool_name : undefined
  const content = typeof payload.content === 'string' ? payload.content : undefined
  const error = typeof payload.error === 'string' ? payload.error : undefined
  const success = payload.success !== false

  return (
    <div className="flex gap-3 py-3 px-4 border-b border-edge-subtle last:border-b-0">
      {/* 左侧时间线指示器 */}
      <div className="flex flex-col items-center shrink-0 pt-0.5">
        <div className={`flex items-center justify-center h-7 w-7 rounded-full bg-surface-tertiary ${colorClass}`}>
          {icon}
        </div>
      </div>

      {/* 右侧内容 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-medium ${colorClass}`}>{label}</span>
          {toolName && (
            <span className="text-xs font-mono text-content-secondary bg-surface-tertiary px-1.5 py-0.5 rounded">
              {toolName}
            </span>
          )}
          <span className="text-[10px] text-content-muted ml-auto shrink-0">
            {new Date(step.receivedAt).toLocaleTimeString()}
          </span>
        </div>

        {/* 工具参数摘要 */}
        {step.eventType === 'tool:start' && !!payload.arguments && (
          <ToolArgsSummary args={payload.arguments as Record<string, unknown>} />
        )}

        {/* 工具结果 */}
        {step.eventType === 'tool:result' && (
          <div className={`mt-1 text-xs leading-5 ${success ? 'text-content-muted' : 'text-red-400'}`}>
            {error && <span className="line-clamp-3">{error}</span>}
            {!error && content && (
              <pre className="whitespace-pre-wrap line-clamp-6 font-mono text-[11px] text-content-secondary bg-surface-tertiary rounded px-2 py-1.5 max-h-[200px] overflow-auto">
                {content.length > 2000 ? content.slice(0, 2000) + '...' : content}
              </pre>
            )}
          </div>
        )}

        {/* LLM 输出 */}
        {step.eventType === 'llm:content' && content && (
          <div className="mt-1 text-xs leading-5 text-content-secondary whitespace-pre-wrap line-clamp-8">
            {content.length > 1000 ? content.slice(0, 1000) + '...' : content}
          </div>
        )}

        {/* 错误 */}
        {step.eventType === 'tool:error' && error && (
          <div className="mt-1 text-xs text-red-400 line-clamp-3">{error}</div>
        )}
      </div>
    </div>
  )
}

/** 工具参数摘要 */
function ToolArgsSummary({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args).slice(0, 3)
  return (
    <div className="mt-1 flex flex-wrap gap-1.5">
      {entries.map(([key, val]) => {
        const display = typeof val === 'string'
          ? (val.length > 80 ? val.slice(0, 80) + '...' : val)
          : JSON.stringify(val)
        return (
          <span key={key} className="inline-flex items-center gap-1 text-[11px] bg-surface-tertiary rounded px-1.5 py-0.5 max-w-[300px]">
            <span className="text-content-muted">{key}:</span>
            <span className="text-content-secondary font-mono truncate">{display}</span>
          </span>
        )
      })}
    </div>
  )
}

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

      {/* 步骤列表 — 类似对话的流式布局 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto"
      >
        {steps.length === 0 && isRunning && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-content-muted">
            <Loader2 className="h-8 w-8 animate-spin text-accent" />
            <p className="text-sm">子 Agent 正在启动...</p>
          </div>
        )}

        {steps.length === 0 && !isRunning && (
          <div className="flex items-center justify-center h-full text-content-muted text-sm">
            暂无执行记录
          </div>
        )}

        {steps.length > 0 && (
          <div className="max-w-[920px] mx-auto w-full py-2">
            {steps.map((step, i) => (
              <StepItem key={`${step.receivedAt}-${i}`} step={step} />
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
