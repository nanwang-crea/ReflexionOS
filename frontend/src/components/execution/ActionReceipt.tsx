import { useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, AlertTriangle, Check, ChevronDown, ChevronRight, Clock3, Loader2, Terminal, X } from 'lucide-react'
import { type ActionReceiptDetail, type ActionReceiptStatus, type ShellApprovalPayload, summarizeReceipt } from './receiptUtils'

export type ApprovalActionType = 'approve' | 'deny'

export interface ApprovalActionPayload {
  runId: string
  approvalId: string
}

interface ActionReceiptProps {
  status: ActionReceiptStatus
  details: ActionReceiptDetail[]
  onApprovalAction?: (action: ApprovalActionType, payload: ApprovalActionPayload) => void
  onDetailClick?: (detail: ActionReceiptDetail) => void
}

export function sendApprovalAction(
  onApprovalAction: ActionReceiptProps['onApprovalAction'],
  action: ApprovalActionType,
  payload: ApprovalActionPayload
) {
  onApprovalAction?.(action, {
    runId: payload.runId,
    approvalId: payload.approvalId,
  })
}

function hasApproval(detail: ActionReceiptDetail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } {
  return detail.approval !== undefined
}

function trimOutput(value: string, maxLength = 800) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}\n...` : value
}

function ShellApprovalDetail({ shell }: { shell: ShellApprovalPayload }) {
  return (
    <div className="mt-2 space-y-1.5 rounded-lg border border-edge bg-surface-tertiary px-3 py-2">
      <div className="flex items-center gap-1.5 text-xs font-medium text-content-secondary">
        <Terminal className="h-3.5 w-3.5" />
        <span className="font-mono">{shell.command}</span>
      </div>
      {shell.execution_mode && (
        <div className="text-xs text-content-muted">
          模式: <span className="font-mono">{shell.execution_mode}</span>
        </div>
      )}
      {shell.reasons && shell.reasons.length > 0 && (
        <div className="text-xs text-content-secondary">
          <span className="font-medium">原因:</span> {shell.reasons.join('；')}
        </div>
      )}
      {shell.risks && shell.risks.length > 0 && (
        <div className="text-xs text-status-warning">
          <span className="font-medium">风险:</span> {shell.risks.join('；')}
        </div>
      )}
    </div>
  )
}

const DETAIL_STATUS_ORDER: Record<string, number> = {
  failed: 0,
  cancelled: 1,
  running: 2,
  waiting_for_approval: 3,
  success: 4,
  pending: 5,
}

function ActionReceiptDetailRow({
  detail,
  onDetailClick,
}: {
  detail: ActionReceiptDetail
  onDetailClick?: (detail: ActionReceiptDetail) => void
}) {
  const hasOutput = !!detail.output
  const hasError = !!detail.error
  const [outputOpen, setOutputOpen] = useState(false)
  const errorInitiallyOpen = detail.status === 'failed' && hasError
  const [errorExpanded, setErrorExpanded] = useState(errorInitiallyOpen)
  const isClickable = onDetailClick != null
    && (detail.category === 'edit' || detail.category === 'create' || detail.category === 'delete')

  return (
    <div
      className={isClickable ? 'cursor-pointer' : ''}
      onClick={isClickable ? () => onDetailClick!(detail) : undefined}
    >
      <div className={`flex flex-wrap items-center gap-2 text-sm ${isClickable ? 'rounded-md px-1 py-0.5 -mx-1 -my-0.5 hover:bg-surface-tertiary transition-colors' : 'text-content-secondary'}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${
          detail.status === 'failed' ? 'bg-status-error' :
          detail.status === 'cancelled' ? 'bg-status-warning' :
          detail.status === 'running' ? 'bg-accent' :
          detail.status === 'waiting_for_approval' ? 'bg-accent' : 'bg-content-muted'
        }`} />
        <span>{detail.summary}</span>
        {detail.duration !== undefined && (
          <span className="text-xs text-content-muted">{detail.duration.toFixed(2)}s</span>
        )}
        {hasOutput && (
          <button
            type="button"
            onClick={() => setOutputOpen(prev => !prev)}
            className="inline-flex items-center gap-0.5 text-xs text-content-muted hover:text-content-secondary transition-colors"
          >
            输出
            {outputOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        )}
        {hasError && (
          <button
            type="button"
            onClick={() => setErrorExpanded(prev => !prev)}
            className="inline-flex items-center gap-0.5 text-xs text-status-error hover:text-status-error transition-colors"
          >
            错误
            {errorExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        )}
      </div>

      <AnimatePresence initial={false}>
        {outputOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <pre className="mt-2 overflow-auto rounded-xl bg-surface-tertiary px-3 py-2 text-xs leading-6 text-content-muted whitespace-pre-wrap">
              {trimOutput(detail.output!)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {errorExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <pre className="mt-2 overflow-auto rounded-xl bg-status-error-soft px-3 py-2 text-xs leading-6 text-status-error whitespace-pre-wrap">
              {trimOutput(detail.error!)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>

      {detail.approval?.shell && (
        <ShellApprovalDetail shell={detail.approval.shell} />
      )}
    </div>
  )
}

export function ActionReceipt({ status, details, onApprovalAction, onDetailClick }: ActionReceiptProps) {
  const [open, setOpen] = useState(false)
  const topRef = useRef<HTMLButtonElement>(null)

  const label = useMemo(() => {
    if (details.length === 1 && status !== 'completed' && status !== 'partial_failed') {
      return details[0].summary
    }
    return summarizeReceipt(details, status)
  }, [details, status])

  const sortedDetails = useMemo(() => {
    return [...details].sort((a, b) => {
      const orderA = DETAIL_STATUS_ORDER[a.status] ?? 99
      const orderB = DETAIL_STATUS_ORDER[b.status] ?? 99
      return orderA - orderB
    })
  }, [details])

  const lineClassName = status === 'failed'
    ? 'text-status-error hover:text-status-error'
    : status === 'partial_failed'
      ? 'text-status-warning hover:text-status-warning'
      : status === 'cancelled'
        ? 'text-status-warning hover:text-status-warning'
        : 'text-content-muted hover:text-content-secondary'

  const approvalDetails = onApprovalAction
    ? details
      .filter((detail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } => (
        detail.status === 'waiting_for_approval' && hasApproval(detail)
      ))
      .map((detail) => ({
        id: detail.id,
        approval: detail.approval,
      }))
    : []

  const handleCollapse = () => {
    setOpen(false)
    // Scroll to top button after close animation
    requestAnimationFrame(() => {
      topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }

  return (
    <div className="mb-8 max-w-[920px]">
      <div className="flex flex-wrap items-center gap-2">
        <button
          ref={topRef}
          type="button"
          onClick={() => setOpen(prev => !prev)}
          className={`group flex items-center gap-2 text-left text-[15px] transition-colors ${lineClassName}`}
        >
          <span>{label}</span>
          <motion.span
            animate={{ rotate: open ? 90 : 0 }}
            transition={{ duration: 0.18 }}
          >
            <ChevronRight className="h-4 w-4" />
          </motion.span>
          {status === 'running' && (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          )}
          {status === 'waiting_for_approval' && (
            <Clock3 className="h-3.5 w-3.5" />
          )}
          {status === 'failed' && (
            <AlertCircle className="h-3.5 w-3.5" />
          )}
          {status === 'partial_failed' && (
            <AlertTriangle className="h-3.5 w-3.5" />
          )}
          {status === 'cancelled' && (
            <AlertCircle className="h-3.5 w-3.5" />
          )}
        </button>

        {approvalDetails.map((detail) => (
          <span key={`${detail.id}-approval`} className="inline-flex items-center gap-1">
            <button
              type="button"
              aria-label="批准此操作"
              title="批准此操作"
              onClick={() => sendApprovalAction(onApprovalAction, 'approve', detail.approval)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-status-success-border text-status-success transition-colors hover:bg-status-success-soft hover:text-status-success focus:outline-none focus:ring-2 focus:ring-status-success/30"
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="拒绝此操作"
              title="拒绝此操作"
              onClick={() => sendApprovalAction(onApprovalAction, 'deny', detail.approval)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-status-error-border text-status-error transition-colors hover:bg-status-error-soft hover:text-status-error focus:outline-none focus:ring-2 focus:ring-status-error/30"
            >
              <X className="h-4 w-4" />
            </button>
          </span>
        ))}
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="mt-3 space-y-3 border-l border-edge pl-4">
              {sortedDetails.map((detail) => (
                <ActionReceiptDetailRow key={detail.id} detail={detail} onDetailClick={onDetailClick} />
              ))}
              <div className="flex justify-center pt-1 pb-2">
                <button
                  type="button"
                  onClick={handleCollapse}
                  className="inline-flex items-center gap-1 text-xs text-content-muted hover:text-content-secondary transition-colors"
                >
                  <ChevronRight className="h-3 w-3 rotate-180" />
                  收起
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
