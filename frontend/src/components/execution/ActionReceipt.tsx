import { memo, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, AlertTriangle, Check, ChevronDown, ChevronRight, Clock3, Loader2, ShieldAlert, ShieldCheck, Terminal, X } from 'lucide-react'
import { type ApprovalActionHandler, type ApprovalActionPayload, type ApprovalActionType, sendApprovalAction } from './approvalActions'
import { type ActionReceiptDetail, type ActionReceiptStatus, type ShellApprovalPayload, summarizeReceipt } from './receiptUtils'

interface ActionReceiptProps {
  status: ActionReceiptStatus
  details: ActionReceiptDetail[]
  onApprovalAction?: ApprovalActionHandler
  onDetailClick?: (detail: ActionReceiptDetail) => void
}

function hasApproval(detail: ActionReceiptDetail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } {
  return detail.approval !== undefined
}

function trimOutput(value: string, maxLength = 800) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}\n...` : value
}

const ShellApprovalDetail = memo(function ShellApprovalDetail({ shell }: { shell: ShellApprovalPayload }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
        <Terminal className="h-4 w-4 shrink-0 text-content-muted" />
        <code className="font-mono text-sm break-all">{shell.command}</code>
      </div>
      {shell.execution_mode && (
        <div className="text-xs text-content-muted pl-6">
          模式: <span className="font-mono">{shell.execution_mode}</span>
        </div>
      )}
      {shell.reasons && shell.reasons.length > 0 && (
        <div className="text-xs text-content-secondary pl-6">
          <span className="font-medium">原因:</span> {shell.reasons.join('；')}
        </div>
      )}
      {shell.risks && shell.risks.length > 0 && (
        <div className="text-xs text-status-warning pl-6">
          <span className="font-medium">风险:</span> {shell.risks.join('；')}
        </div>
      )}
    </div>
  )
})

const DETAIL_STATUS_ORDER: Record<string, number> = {
  failed: 0,
  cancelled: 1,
  running: 2,
  waiting_for_approval: 3,
  success: 4,
  pending: 5,
}

const ActionReceiptDetailRow = memo(function ActionReceiptDetailRow({
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

      {detail.data?.screenshot_path && (
        <div className="mt-2">
          <img
            src={`/api/browser/screenshot?path=${encodeURIComponent(detail.data.screenshot_path as string)}`}
            alt="Browser screenshot"
            className="max-w-sm rounded border border-edge cursor-pointer hover:opacity-80"
            onClick={() => window.open(`/api/browser/screenshot?path=${encodeURIComponent(detail.data!.screenshot_path as string)}`, '_blank')}
          />
          <p className="mt-1 text-xs text-content-tertiary">
            {detail.data.width as number}x{detail.data.height as number} — 点击查看原图
          </p>
        </div>
      )}
    </div>
  )
})

const ApprovalCard = memo(function ApprovalCard({
  details,
  onApprovalAction,
}: {
  details: ActionReceiptDetail[]
  onApprovalAction: (action: ApprovalActionType, payload: ApprovalActionPayload) => void
}) {
  const approvalDetails = useMemo(() =>
    details
      .filter((detail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } => (
        detail.status === 'waiting_for_approval' && hasApproval(detail)
      ))
      .map((detail) => ({
        id: detail.id,
        approval: detail.approval,
        shell: detail.approval.shell,
      })),
    [details]
  )

  const summary = useMemo(() => summarizeReceipt(details, 'waiting_for_approval'), [details])

  return (
    <div className="mb-8 max-w-[920px] mx-auto w-full rounded-xl border border-edge bg-surface-primary overflow-hidden">
      <div className="flex flex-col gap-3 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
          <ShieldAlert className="h-4 w-4 shrink-0 text-content-muted" />
          <span>需要批准执行命令</span>
        </div>
        <p className="text-sm text-content-muted">{summary}</p>

        {approvalDetails.map((detail) => (
          <div key={detail.id} className="rounded-lg border border-edge bg-surface-secondary px-3 py-2">
            {detail.shell && <ShellApprovalDetail shell={detail.shell} />}
          </div>
        ))}
      </div>

      <div className="border-t border-edge bg-surface-secondary px-4 py-3">
        {approvalDetails.map((detail) => (
          <div key={detail.id} className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => sendApprovalAction(onApprovalAction, 'approve', detail.approval)}
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              <Check className="h-3.5 w-3.5" />
              允许一次
            </button>
            <button
              type="button"
              onClick={() => sendApprovalAction(onApprovalAction, 'trust', detail.approval)}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-accent bg-surface-primary px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent/10 focus:outline-none focus:ring-2 focus:ring-accent/30"
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              此会话允许
            </button>
            {detail.shell && detail.approval.suggestedTrust?.prefix && (
              <span className="text-xs text-content-muted">
                将信任: {detail.approval.suggestedTrust.prefix.join(', ')}
              </span>
            )}
            <button
              type="button"
              onClick={() => sendApprovalAction(onApprovalAction, 'deny', detail.approval)}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-edge bg-surface-primary px-3 py-1.5 text-sm font-medium text-content-secondary transition-colors hover:bg-surface-tertiary focus:outline-none focus:ring-2 focus:ring-accent/30"
            >
              <X className="h-3.5 w-3.5" />
              拒绝
            </button>
          </div>
        ))}
      </div>
    </div>
  )
})

export const ActionReceipt = memo(function ActionReceipt({ status, details, onApprovalAction, onDetailClick }: ActionReceiptProps) {
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

  const handleCollapse = () => {
    setOpen(false)
    requestAnimationFrame(() => {
      topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }

  if (status === 'waiting_for_approval' && onApprovalAction) {
    return <ApprovalCard details={details} onApprovalAction={onApprovalAction} />
  }

  return (
    <div className="mb-8 max-w-[920px] mx-auto w-full">
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
})
