import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, CheckCircle2, ChevronDown, Loader2 } from 'lucide-react'
import { buildThoughtPreview } from '@/components/StreamingMessage'
import { StepRow, type StepRowStatus } from './StepRow'

export type ExecutionTraceStatus = 'thinking' | 'running' | 'completed' | 'failed'

export interface ExecutionTraceStep {
  id: string
  stepNumber: number
  toolName: string
  status: StepRowStatus
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, any>
}

interface ExecutionTraceProps {
  status: ExecutionTraceStatus
  thought?: string
  thoughtStreaming?: boolean
  steps: ExecutionTraceStep[]
}

function findActiveStep(steps: ExecutionTraceStep[]) {
  for (const step of steps) {
    if (step.status === 'running') {
      return step
    }
  }

  return null
}

function getStatusCopy(status: ExecutionTraceStatus, steps: ExecutionTraceStep[]) {
  const recentTools = steps.slice(-3).map(step => step.toolName).join(' / ')
  const countLabel = steps.length > 0 ? `${steps.length} 步` : ''

  const prefix = {
    thinking: '思考中',
    running: '执行中',
    completed: '执行完成',
    failed: '执行失败'
  }[status]

  return [prefix, countLabel, recentTools].filter(Boolean).join(' · ')
}

function TraceIcon({ status }: { status: ExecutionTraceStatus }) {
  if (status === 'thinking' || status === 'running') {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-50 text-blue-600">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      </span>
    )
  }

  if (status === 'failed') {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-red-50 text-red-600">
        <AlertCircle className="h-3.5 w-3.5" />
      </span>
    )
  }

  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
      <CheckCircle2 className="h-3.5 w-3.5" />
    </span>
  )
}

export function ExecutionTrace({
  status,
  thought = '',
  thoughtStreaming = false,
  steps
}: ExecutionTraceProps) {
  const [detailsOpen, setDetailsOpen] = useState(false)

  const activeStep = useMemo(() => findActiveStep(steps), [steps])
  const summary = useMemo(() => getStatusCopy(status, steps), [status, steps])
  const preview = useMemo(
    () => buildThoughtPreview(thought, thoughtStreaming),
    [thought, thoughtStreaming]
  )

  return (
    <div className="mb-3 max-w-[80%] rounded-2xl border border-slate-200 bg-white/95 text-slate-800">
      <div className="flex items-start gap-3 px-3 py-2.5">
        <TraceIcon status={status} />

        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-slate-700">
            {summary}
          </div>
          <div className="mt-0.5 truncate text-xs text-slate-500">
            {preview}
          </div>
        </div>

        {steps.length > 0 && (
          <button
            type="button"
            onClick={() => setDetailsOpen(prev => !prev)}
            className="flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          >
            <span>{detailsOpen ? '收起详情' : '查看详情'}</span>
            <motion.span
              animate={{ rotate: detailsOpen ? 180 : 0 }}
              transition={{ duration: 0.18 }}
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </motion.span>
          </button>
        )}
      </div>

      {!detailsOpen && activeStep && (
        <div className="border-t border-slate-100 px-3 py-2">
          <StepRow
            stepNumber={activeStep.stepNumber}
            toolName={activeStep.toolName}
            status={activeStep.status}
            output={activeStep.output}
            error={activeStep.error}
            duration={activeStep.duration}
            arguments={activeStep.arguments}
            defaultExpanded
            autoCollapse
          />
        </div>
      )}

      <AnimatePresence initial={false}>
        {detailsOpen && steps.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-slate-100"
          >
            <div className="space-y-1.5 px-3 py-2.5">
              {steps.map((step) => (
                <StepRow
                  key={step.id}
                  stepNumber={step.stepNumber}
                  toolName={step.toolName}
                  status={step.status}
                  output={step.output}
                  error={step.error}
                  duration={step.duration}
                  arguments={step.arguments}
                />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
