/**
 * DelegateToolCall — delegate 工具的专属 UI 组件
 *
 * 当主 Agent 通过 delegate 工具委托子任务时：
 * - 执行中：显示"子 Agent 运行中"可点击指示器，点击进入二级对话页面查看实时输出
 * - 成功：显示子任务完成 + 可展开输出
 * - 失败：显示错误信息 + 可展开详情
 */
import { memo, useCallback, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, Loader2, AlertCircle, CheckCircle2, Users, ExternalLink } from 'lucide-react'
import type { SubAgentStep } from '@/hooks/useSubAgentEvents'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
import { useSubAgentSteps } from '@/hooks/useSubAgentEvents'

/**
 * 从子 Agent 事件流中提取真实的工具执行步数
 *
 * 后端在 tool:start / tool:result / tool:error 事件的 payload 中携带 step_number，
 * 取所有事件中的最大值即为已完成的工具步数。llm:reasoning / llm:content 等流式
 * 事件没有 step_number，不应被计入。
 */
export function getSubAgentToolStepCount(steps: SubAgentStep[]): number {
  let maxStep = 0
  for (const step of steps) {
    const n = step.payload?.step_number
    if (typeof n === 'number' && n > maxStep) maxStep = n
  }
  return maxStep
}
import { SubAgentDetailPanel } from './SubAgentDetailPanel'

interface DelegateToolCallProps {
  detail: ActionReceiptDetail
  /** delegate 的 arguments（从 payloadJson.arguments 解析） */
  args?: Record<string, unknown>
}

function truncateText(text: string, maxLen: number): string {
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

export const DelegateToolCall = memo(function DelegateToolCall({ detail, args }: DelegateToolCallProps) {
  const [expanded, setExpanded] = useState(false)
  const [showDetail, setShowDetail] = useState(false)

  const task = typeof args?.task === 'string' ? args.task : ''
  const expectedOutput = typeof args?.expected_output === 'string' ? args.expected_output : ''
  const isRunning = detail.status === 'running'
  const isFailed = detail.status === 'failed' || detail.status === 'cancelled'
  const isSuccess = detail.status === 'success'

  const hasOutput = !!detail.output
  const hasError = !!detail.error

  // 从全局 zustand store 订阅该 delegate 调用的子 agent 实时步骤
  // 使用 tool_call_id 关联 sub_agent 事件（存于 detail.data 中）
  // detail.id 是 message.id，而 store 以 tool_call_id 为 key
  const callId = (detail.data?.tool_call_id as string) || detail.id
  const subAgentSteps = useSubAgentSteps(callId)
  const hasSteps = subAgentSteps.length > 0
  // 使用后端发送的真实 step_number 而非事件总数，避免流式 chunk 虚增步数
  const toolStepCount = getSubAgentToolStepCount(subAgentSteps)

  const handleCloseDetail = useCallback(() => setShowDetail(false), [])

  return (
    <>
      <div className="max-w-[920px] mx-auto w-full rounded-xl border border-edge bg-surface-primary overflow-hidden">
        {/* 头部：状态 + 任务描述 */}
        <div className="flex items-start gap-3 px-4 py-3">
          <div className="mt-0.5 shrink-0">
            {isRunning && <Loader2 className="h-4 w-4 animate-spin text-accent" />}
            {isSuccess && <CheckCircle2 className="h-4 w-4 text-status-success" />}
            {isFailed && <AlertCircle className="h-4 w-4 text-status-error" />}
            {!isRunning && !isSuccess && !isFailed && <Users className="h-4 w-4 text-content-muted" />}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-content-primary">
                {isRunning ? '正在执行子任务' : isFailed ? '子任务失败' : '子任务完成'}
              </span>
              {detail.duration !== undefined && (
                <span className="text-xs text-content-muted">{detail.duration.toFixed(1)}s</span>
              )}
            </div>

            {task && (
              <p className="mt-1 text-sm text-content-secondary break-words">
                {truncateText(task, 200)}
              </p>
            )}

            {expectedOutput && (
              <p className="mt-1 text-xs text-content-muted">
                预期: {truncateText(expectedOutput, 120)}
              </p>
            )}
          </div>

          {/* 展开/收起按钮（完成/失败后显示输出详情） */}
          {(hasOutput || hasError) && !isRunning && (
            <button
              type="button"
              onClick={() => setExpanded(prev => !prev)}
              className="shrink-0 p-1 text-content-muted hover:text-content-secondary transition-colors"
            >
              <motion.span animate={{ rotate: expanded ? 90 : 0 }} transition={{ duration: 0.15 }}>
                <ChevronRight className="h-4 w-4" />
              </motion.span>
            </button>
          )}
        </div>

        {/* 子 Agent 运行中指示器 — 点击进入二级对话页面 */}
        {isRunning && (
          <button
            type="button"
            onClick={() => setShowDetail(true)}
            className="w-full border-t border-edge px-4 py-2.5 flex items-center gap-2.5 text-left hover:bg-surface-secondary/50 transition-colors group"
          >
            <Loader2 className="h-3.5 w-3.5 animate-spin text-accent shrink-0" />
            <span className="text-xs font-medium text-content-secondary">
              子 Agent 运行中
            </span>
            {hasSteps && toolStepCount > 0 && (
              <span className="text-[10px] text-content-muted bg-surface-tertiary px-1.5 py-0.5 rounded-full">
                {toolStepCount} 步
              </span>
            )}
            {!hasSteps && (
              <span className="text-[10px] text-content-muted">
                正在启动...
              </span>
            )}
            <ExternalLink className="h-3 w-3 text-content-muted ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
        )}

        {/* 已完成的子 agent — 如果有历史步骤，显示可点击的回顾入口 */}
        {!isRunning && hasSteps && (
          <button
            type="button"
            onClick={() => setShowDetail(true)}
            className="w-full border-t border-edge px-4 py-2 flex items-center gap-2 text-left hover:bg-surface-secondary/50 transition-colors"
          >
            <Users className="h-3.5 w-3.5 text-content-muted shrink-0" />
            <span className="text-xs text-content-muted">
              查看执行过程 ({toolStepCount > 0 ? toolStepCount : subAgentSteps.length} 步)
            </span>
            <ExternalLink className="h-3 w-3 text-content-muted ml-auto" />
          </button>
        )}

        {/* 可展开区域：输出 / 错误 */}
        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="overflow-hidden"
            >
              <div className="border-t border-edge px-4 py-3 space-y-2">
                {hasOutput && (
                  <div>
                    <div className="text-xs font-medium text-content-muted mb-1">输出</div>
                    <pre className="overflow-auto rounded-lg bg-surface-tertiary px-3 py-2 text-xs leading-5 text-content-secondary whitespace-pre-wrap max-h-[400px]">
                      {detail.output}
                    </pre>
                  </div>
                )}
                {hasError && (
                  <div>
                    <div className="text-xs font-medium text-status-error mb-1">错误</div>
                    <pre className="overflow-auto rounded-lg bg-status-error-soft px-3 py-2 text-xs leading-5 text-status-error whitespace-pre-wrap">
                      {detail.error}
                    </pre>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* 二级对话页面 — 全屏 overlay 展示子 agent 实时执行详情 */}
      {showDetail && (
        <SubAgentDetailPanel
          task={task}
          steps={subAgentSteps}
          isRunning={isRunning}
          onClose={handleCloseDetail}
        />
      )}
    </>
  )
})
