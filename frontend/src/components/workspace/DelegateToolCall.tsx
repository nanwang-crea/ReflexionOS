import { memo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, Loader2, AlertCircle, CheckCircle2, Users } from 'lucide-react'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'

/**
 * DelegateToolCall — delegate 工具的专属 UI 组件
 *
 * 当主 Agent 通过 delegate 工具委托子任务时，以折叠卡片形式展示：
 * - 执行中：显示 spinner + 任务描述
 * - 成功：显示子任务完成 + 可展开输出
 * - 失败：显示错误信息 + 可展开详情
 */

interface DelegateToolCallProps {
  detail: ActionReceiptDetail
  /** delegate 的 arguments（从 payloadJson.arguments 解析） */
  args?: Record<string, unknown>
}

function truncateText(text: string, maxLen: number): string {
  return text.length > maxLen ? text.slice(0, maxLen) + '…' : text
}

export const DelegateToolCall = memo(function DelegateToolCall({ detail, args }: DelegateToolCallProps) {
  const [expanded, setExpanded] = useState(false)

  const task = typeof args?.task === 'string' ? args.task : ''
  const expectedOutput = typeof args?.expected_output === 'string' ? args.expected_output : ''
  const isRunning = detail.status === 'running'
  const isFailed = detail.status === 'failed' || detail.status === 'cancelled'
  const isSuccess = detail.status === 'success'

  const hasOutput = !!detail.output
  const hasError = !!detail.error

  return (
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

        {/* 展开/收起按钮 */}
        {(hasOutput || hasError) && (
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
  )
})
