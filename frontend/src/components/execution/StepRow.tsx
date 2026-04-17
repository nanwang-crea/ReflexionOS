import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, Check, ChevronRight, Clock3, Loader2 } from 'lucide-react'

export type StepRowStatus = 'pending' | 'running' | 'success' | 'failed'

interface StepRowProps {
  stepNumber: number
  toolName: string
  status: StepRowStatus
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, any>
  defaultExpanded?: boolean
  autoCollapse?: boolean
}

const statusStyles = {
  pending: {
    icon: Clock3,
    iconClassName: 'text-slate-400',
    markerClassName: 'bg-slate-200',
    label: '等待中',
    labelClassName: 'bg-slate-100 text-slate-500'
  },
  running: {
    icon: Loader2,
    iconClassName: 'text-blue-600',
    markerClassName: 'bg-blue-500',
    label: '运行中',
    labelClassName: 'bg-blue-50 text-blue-700'
  },
  success: {
    icon: Check,
    iconClassName: 'text-emerald-600',
    markerClassName: 'bg-emerald-500',
    label: '完成',
    labelClassName: 'bg-emerald-50 text-emerald-700'
  },
  failed: {
    icon: AlertCircle,
    iconClassName: 'text-red-600',
    markerClassName: 'bg-red-500',
    label: '失败',
    labelClassName: 'bg-red-50 text-red-700'
  }
} as const

export function StepRow({
  stepNumber,
  toolName,
  status,
  output,
  error,
  duration,
  arguments: args,
  defaultExpanded = false,
  autoCollapse = false
}: StepRowProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  const hasArguments = Boolean(args && Object.keys(args).length > 0)
  const hasContent = hasArguments || Boolean(output) || Boolean(error)
  const style = statusStyles[status]
  const Icon = style.icon

  useEffect(() => {
    if (status === 'running' && defaultExpanded) {
      setIsExpanded(true)
    }
  }, [defaultExpanded, status, stepNumber])

  useEffect(() => {
    if (!autoCollapse || status === 'running' || !hasContent) {
      return
    }

    const timer = window.setTimeout(() => {
      setIsExpanded(false)
    }, 1200)

    return () => window.clearTimeout(timer)
  }, [autoCollapse, hasContent, status])

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200/80 bg-slate-50/80">
      <button
        type="button"
        onClick={() => hasContent && setIsExpanded(prev => !prev)}
        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left ${
          hasContent ? 'cursor-pointer hover:bg-white/80' : 'cursor-default'
        }`}
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${style.markerClassName}`} />
        <span className="w-6 shrink-0 text-[11px] font-medium tabular-nums text-slate-400">
          {String(stepNumber).padStart(2, '0')}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm text-slate-700">
          {toolName}
        </span>
        {status !== 'success' && (
          <span className={`rounded-full px-1.5 py-0.5 text-[11px] ${style.labelClassName}`}>
            {style.label}
          </span>
        )}
        {duration !== undefined && (
          <span className="shrink-0 text-[11px] text-slate-400">
            {duration.toFixed(2)}s
          </span>
        )}
        <span className="flex h-4 w-4 shrink-0 items-center justify-center">
          <Icon
            className={`h-3.5 w-3.5 ${style.iconClassName} ${
              status === 'running' ? 'animate-spin' : ''
            }`}
          />
        </span>
        {hasContent && (
          <motion.span
            animate={{ rotate: isExpanded ? 90 : 0 }}
            transition={{ duration: 0.18 }}
            className="shrink-0 text-slate-300"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </motion.span>
        )}
      </button>

      <AnimatePresence initial={false}>
        {isExpanded && hasContent && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="border-t border-slate-200/80"
          >
            <div className="space-y-2 px-3 py-2.5">
              {hasArguments && (
                <div className="text-xs text-slate-600">
                  <div className="mb-1 font-medium text-slate-500">参数</div>
                  <pre className="overflow-auto rounded-md bg-white px-2.5 py-2 text-[11px] leading-5 text-slate-600">
                    {JSON.stringify(args, null, 2)}
                  </pre>
                </div>
              )}

              {output && (
                <div className="text-xs text-slate-600">
                  <div className="mb-1 font-medium text-slate-500">输出</div>
                  <pre className="max-h-48 overflow-auto rounded-md bg-white px-2.5 py-2 text-[11px] leading-5 text-slate-600 whitespace-pre-wrap">
                    {output}
                  </pre>
                </div>
              )}

              {error && (
                <div className="text-xs text-red-700">
                  <div className="mb-1 font-medium text-red-600">错误</div>
                  <pre className="overflow-auto rounded-md bg-red-50 px-2.5 py-2 text-[11px] leading-5 whitespace-pre-wrap">
                    {error}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
