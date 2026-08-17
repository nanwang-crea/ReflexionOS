/**
 * 文件功能：任务计划进度展示组件
 * 文件描述：展示当前会话计划（Plan）的执行进度，包括完整展开的步骤列表（PlanProgress）
 *          和最小化后的一行摘要条（PlanMinimizedBar）
 * 核心逻辑：按步骤状态（completed/in_progress/pending/blocked）渲染对应图标与文案样式，
 *          并统计已完成/阻塞数量用于摘要展示
 */
import { memo, useCallback } from 'react'
import { motion } from 'framer-motion'
import type { Plan } from '@/types/conversation'
import { Check, Circle, ListChecks, Loader2, Minimize2, XCircle } from 'lucide-react'

interface PlanProgressProps {
  plan: Plan
  isMinimized: boolean
  onToggleMinimize: () => void
}

/**
 * 组件名：PlanProgress
 * 入参（props）：
 *   - plan (Plan): 当前计划数据，包含步骤列表
 *   - isMinimized (boolean): 是否处于最小化状态，为 true 时不渲染（由 PlanMinimizedBar 代替展示）
 *   - onToggleMinimize (() => void): 点击“缩小计划面板”按钮时的回调
 * 作用/渲染逻辑：
 *   1. 统计已完成、阻塞、总步骤数量，用于顶部摘要文案
 *   2. 顶部展示摘要与缩小按钮，下方以有序列表展示每个步骤（图标 + 文案），
 *      已完成步骤加删除线并展示 findings（若有），不同状态使用不同图标与文字颜色
 * 返回值：JSX.Element | null - 计划进度面板；isMinimized 为 true 时返回 null
 */
export const PlanProgress = memo(function PlanProgress({ plan, isMinimized, onToggleMinimize }: PlanProgressProps) {
  const completedCount = plan.steps.filter((s) => s.status === 'completed').length
  const blockedCount = plan.steps.filter((s) => s.status === 'blocked').length
  const totalCount = plan.steps.length

  if (isMinimized) {
    return null
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 14, scale: 0.98 }}
      transition={{ duration: 0.2 }}
      className="sticky bottom-4 z-10 mx-auto mt-10 mb-4 w-full max-w-[920px] rounded-[28px] border border-edge bg-surface-primary/95 px-6 py-4 shadow-theme backdrop-blur"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2 text-content-muted">
          <ListChecks className="h-4 w-4 shrink-0 text-content-secondary" />
          <span className="truncate text-[15px]">
            共 {totalCount} 个任务，已完成 {completedCount} 个
            {blockedCount > 0 && `，阻塞 ${blockedCount} 个`}
          </span>
        </div>
        <button
          type="button"
          onClick={onToggleMinimize}
          title="缩小计划面板"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-content-muted transition-colors hover:bg-surface-tertiary hover:text-content-secondary"
        >
          <Minimize2 className="h-4 w-4" />
        </button>
      </div>
      <ol className="mt-4 max-h-[40vh] overflow-y-auto space-y-2 pr-2">
        {plan.steps.map((step, index) => (
          <li
            key={index}
            className={[
              'flex items-start gap-3 text-[15px] leading-7',
              step.status === 'completed' && 'text-content-muted',
               step.status === 'in_progress' && 'font-medium text-content-primary',
               step.status === 'pending' && 'text-content-muted',
              step.status === 'blocked' && 'text-status-error',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span className="mt-1.5 shrink-0">
              {step.status === 'completed' && (
                <Check className="h-4 w-4 text-content-muted" />
              )}
              {step.status === 'in_progress' && (
                <Loader2 className="h-4 w-4 animate-spin text-content-muted" />
              )}
              {step.status === 'pending' && (
                <Circle className="h-4 w-4 text-content-muted" />
              )}
              {step.status === 'blocked' && (
                <XCircle className="h-4 w-4 text-status-error" />
              )}
            </span>
            <div className="min-w-0">
              <span className={step.status === 'completed' ? 'line-through' : ''}>
                {index + 1}. {step.content}
              </span>
              {step.status === 'completed' && step.findings && (
                <div className="mt-1 text-sm text-content-muted">
                  → {step.findings}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </motion.div>
  )
})

/**
 * 组件名：PlanMinimizedBar
 * 入参（props）：
 *   - plan (Plan): 当前计划数据，包含步骤列表
 *   - onExpand (() => void): 点击展开时的回调
 * 作用/渲染逻辑：
 *   在聊天输入框上方展示一行紧凑摘要条（总数/已完成数/当前进行中步骤），点击可展开完整计划面板
 * 返回值：JSX.Element - 最小化状态下的计划摘要条
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
  const currentStepIndex = currentStep ? plan.steps.indexOf(currentStep) : -1

  const handleClick = useCallback(() => {
    onExpand()
  }, [onExpand])

  return (
    <button
      type="button"
      onClick={handleClick}
      title="展开计划面板"
      className="flex w-full items-center gap-2 border-b border-edge-subtle bg-surface-secondary/80 px-4 py-2 text-left text-sm text-content-secondary backdrop-blur transition-colors hover:bg-surface-tertiary"
    >
      <ListChecks className="h-3.5 w-3.5 shrink-0 text-content-muted" />
      <span className="truncate">
        共 {totalCount} 个任务，已完成 {completedCount} 个
        {currentStep && (
          <span className="ml-1 text-content-muted">
            · 当前: {currentStepIndex + 1}. {currentStep.content}
          </span>
        )}
      </span>
      <span className="ml-auto shrink-0 text-content-muted">
        <Minimize2 className="h-3.5 w-3.5 rotate-180" />
      </span>
    </button>
  )
})
