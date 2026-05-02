import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, Check, ChevronRight, Clock3, Loader2, Terminal, X } from 'lucide-react'
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
    <div className="mt-2 space-y-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-700">
        <Terminal className="h-3.5 w-3.5" />
        <span className="font-mono">{shell.command}</span>
      </div>
      {shell.execution_mode && (
        <div className="text-xs text-slate-500">
          模式: <span className="font-mono">{shell.execution_mode}</span>
        </div>
      )}
      {shell.reasons && shell.reasons.length > 0 && (
        <div className="text-xs text-slate-600">
          <span className="font-medium">原因:</span> {shell.reasons.join('；')}
        </div>
      )}
      {shell.risks && shell.risks.length > 0 && (
        <div className="text-xs text-amber-700">
          <span className="font-medium">风险:</span> {shell.risks.join('；')}
        </div>
      )}
    </div>
  )
}

export function ActionReceipt({ status, details, onApprovalAction }: ActionReceiptProps) {
  const [open, setOpen] = useState(false)
  const label = useMemo(() => {
    if (details.length === 1 && status !== 'completed') {
      return details[0].summary
    }
    return summarizeReceipt(details, status)
  }, [details, status])

  const lineClassName = status === 'failed'
    ? 'text-red-500 hover:text-red-600'
    : status === 'cancelled'
      ? 'text-amber-500 hover:text-amber-600'
      : 'text-slate-400 hover:text-slate-600'
  const approvalDetails = status === 'waiting_for_approval' && onApprovalAction
    ? details
      .filter((detail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } => (
        detail.status === 'waiting_for_approval' && hasApproval(detail)
      ))
      .map((detail) => ({
        id: detail.id,
        approval: detail.approval,
      }))
    : []

  return (
    <div className="mb-8 max-w-[920px]">
      <div className="flex flex-wrap items-center gap-2">
        <button
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
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-emerald-200 text-emerald-600 transition-colors hover:bg-emerald-50 hover:text-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-200"
            >
              <Check className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="拒绝此操作"
              title="拒绝此操作"
              onClick={() => sendApprovalAction(onApprovalAction, 'deny', detail.approval)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-rose-200 text-rose-600 transition-colors hover:bg-rose-50 hover:text-rose-700 focus:outline-none focus:ring-2 focus:ring-rose-200"
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
            <div className="mt-3 space-y-3 border-l border-slate-200 pl-4">
              {details.map((detail) => (
                <div key={detail.id}>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                    <span className={`h-1.5 w-1.5 rounded-full ${
                      detail.status === 'failed' ? 'bg-red-400' :
                      detail.status === 'cancelled' ? 'bg-amber-400' :
                      detail.status === 'running' ? 'bg-blue-400' :
                      detail.status === 'waiting_for_approval' ? 'bg-indigo-400' : 'bg-slate-300'
                    }`} />
                    <span>{detail.summary}</span>
                    {detail.duration !== undefined && (
                      <span className="text-xs text-slate-400">{detail.duration.toFixed(2)}s</span>
                    )}
                  </div>

                  {detail.output && (
                    <pre className="mt-2 overflow-auto rounded-xl bg-slate-50 px-3 py-2 text-xs leading-6 text-slate-500 whitespace-pre-wrap">
                      {trimOutput(detail.output)}
                    </pre>
                  )}

                  {detail.error && (
                    <pre className="mt-2 overflow-auto rounded-xl bg-red-50 px-3 py-2 text-xs leading-6 text-red-600 whitespace-pre-wrap">
                      {trimOutput(detail.error)}
                    </pre>
                  )}

                  {detail.approval?.shell && (
                    <ShellApprovalDetail shell={detail.approval.shell} />
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
