import { memo, useCallback } from 'react'
import { motion } from 'framer-motion'
import type { Plan } from '@/types/conversation'
import { Check, Circle, ListChecks, Loader2, Minimize2, XCircle } from 'lucide-react'

interface PlanProgressProps {
  plan: Plan
  isMinimized: boolean
  onToggleMinimize: () => void
}

export const PlanProgress = memo(function PlanProgress({ plan, isMinimized, onToggleMinimize }: PlanProgressProps) {
  const completedCount = plan.steps.filter((s) => s.status === 'completed').length
  const totalCount = plan.steps.length

  // When minimized, the plan is shown as a compact bar above the input
  // (rendered by AgentWorkspace), so we render nothing here.
  if (isMinimized) {
    return null
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 14, scale: 0.98 }}
      transition={{ duration: 0.2 }}
      className="sticky bottom-4 z-10 mx-auto mt-10 mb-4 w-full max-w-[920px] rounded-[28px] border border-slate-200 bg-white/95 px-6 py-4 shadow-[0_18px_60px_rgba(15,23,42,0.12)] backdrop-blur"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2 text-slate-500">
          <ListChecks className="h-4 w-4 shrink-0 text-slate-700" />
          <span className="truncate text-[15px]">
            共 {totalCount} 个任务，已经完成 {completedCount} 个
          </span>
        </div>
        <button
          type="button"
          onClick={onToggleMinimize}
          title="缩小计划面板"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <Minimize2 className="h-4 w-4" />
        </button>
      </div>
      <ol className="mt-4 max-h-72 overflow-y-auto space-y-2 pr-2">
        {plan.steps.map((step) => (
          <li
            key={step.id}
            className={[
              'flex items-start gap-3 text-[15px] leading-7',
              step.status === 'completed' && 'text-slate-300',
              step.status === 'in_progress' && 'font-medium text-slate-900',
              step.status === 'pending' && 'text-slate-500',
              step.status === 'blocked' && 'text-red-500',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span className="mt-1.5 shrink-0">
              {step.status === 'completed' && (
                <Check className="h-4 w-4 text-slate-300" />
              )}
              {step.status === 'in_progress' && (
                <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
              )}
              {step.status === 'pending' && (
                <Circle className="h-4 w-4 text-slate-500" />
              )}
              {step.status === 'blocked' && (
                <XCircle className="h-4 w-4 text-red-400" />
              )}
            </span>
            <div className="min-w-0">
              <span className={step.status === 'completed' ? 'line-through' : ''}>
                {step.id}. {step.description}
              </span>
              {step.findings && (
                <p className="mt-0.5 text-sm text-slate-400 no-underline">
                  {step.findings}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </motion.div>
  )
})

/**
 * A compact bar shown above the chat input when the plan is minimized.
 * Displays a one-line summary and the current step, with a button to expand.
 */
export const PlanMinimizedBar = memo(function PlanMinimizedBar({
  plan,
  onExpand,
}: {
  plan: Plan
  onExpand: () => void
}) {
  const completedCount = plan.steps.filter((s) => s.status === 'completed').length
  const totalCount = plan.steps.length
  const currentStep = plan.steps.find((s) => s.status === 'in_progress')

  const handleClick = useCallback(() => {
    onExpand()
  }, [onExpand])

  return (
    <button
      type="button"
      onClick={handleClick}
      title="展开计划面板"
      className="flex w-full items-center gap-2 border-b border-slate-100 bg-slate-50/80 px-4 py-2 text-left text-sm text-slate-600 backdrop-blur transition-colors hover:bg-slate-100"
    >
      <ListChecks className="h-3.5 w-3.5 shrink-0 text-slate-500" />
      <span className="truncate">
        共 {totalCount} 个任务，已完成 {completedCount} 个
        {currentStep && (
          <span className="ml-1 text-slate-400">
            · 当前: {currentStep.id}. {currentStep.description}
          </span>
        )}
      </span>
      <span className="ml-auto shrink-0 text-slate-400">
        <Minimize2 className="h-3.5 w-3.5 rotate-180" />
      </span>
    </button>
  )
})
