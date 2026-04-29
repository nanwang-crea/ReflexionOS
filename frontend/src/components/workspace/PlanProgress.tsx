import { motion } from 'framer-motion'
import type { Plan } from '@/types/conversation'
import { Check, Circle, Loader2, XCircle } from 'lucide-react'

interface PlanProgressProps {
  plan: Plan
}

export function PlanProgress({ plan }: PlanProgressProps) {
  const completedCount = plan.steps.filter((s) => s.status === 'completed').length
  const totalCount = plan.steps.length

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 20, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="fixed bottom-24 right-6 z-10 w-72 rounded-xl border border-slate-200 bg-white shadow-lg"
    >
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-slate-700 truncate pr-2">
            {plan.goal}
          </h3>
          <span className="shrink-0 text-xs text-slate-400">
            {completedCount}/{totalCount}
          </span>
        </div>
        {/* Progress bar */}
        <div className="mt-2 h-1 rounded-full bg-slate-100">
          <div
            className="h-1 rounded-full bg-emerald-400 transition-all duration-300"
            style={{ width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }}
          />
        </div>
      </div>
      <ol className="max-h-60 overflow-y-auto px-4 py-3 space-y-2">
        {plan.steps.map((step) => (
          <li
            key={step.id}
            className={[
              'flex items-start gap-2 text-sm',
              step.status === 'completed' && 'text-slate-400',
              step.status === 'in_progress' && 'text-slate-900 font-medium',
              step.status === 'pending' && 'text-slate-400',
              step.status === 'blocked' && 'text-red-500',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span className="mt-0.5 shrink-0">
              {step.status === 'completed' && (
                <Check className="h-3.5 w-3.5 text-emerald-500" />
              )}
              {step.status === 'in_progress' && (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
              )}
              {step.status === 'pending' && (
                <Circle className="h-3.5 w-3.5 text-slate-300" />
              )}
              {step.status === 'blocked' && (
                <XCircle className="h-3.5 w-3.5 text-red-400" />
              )}
            </span>
            <div className="min-w-0">
              <span className={step.status === 'completed' ? 'line-through' : ''}>
                {step.description}
              </span>
              {step.findings && (
                <p className="mt-0.5 text-xs text-slate-500 no-underline">
                  → {step.findings}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </motion.div>
  )
}
