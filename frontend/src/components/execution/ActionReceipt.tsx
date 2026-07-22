import { memo, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, AlertTriangle, Check, ChevronDown, ChevronRight, Clock3, FolderLock, Globe, Loader2, ShieldAlert, ShieldCheck, Terminal, X } from 'lucide-react'
import { type ApprovalActionHandler, type ApprovalActionPayload, type ApprovalActionType, sendApprovalAction } from './approvalActions'
import { type ActionReceiptDetail, type ActionReceiptStatus, type SandboxNetworkPayload, type SandboxPathPayload, type ShellApprovalPayload, summarizeReceipt } from './receiptUtils'

interface ActionReceiptProps {
  status: ActionReceiptStatus
  details: ActionReceiptDetail[]
  onApprovalAction?: ApprovalActionHandler
  onDetailClick?: (detail: ActionReceiptDetail) => void
  /** 是否为子代理的审批，用于区分标题显示 */
  isSubAgent?: boolean
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

const SandboxNetworkDetail = memo(function SandboxNetworkDetail({ payload }: { payload: SandboxNetworkPayload }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
        <Globe className="h-4 w-4 shrink-0 text-content-muted" />
        <code className="font-mono text-sm break-all">{payload.command}</code>
      </div>
      <div className="text-xs text-status-warning pl-6">
        沙箱阻止了网络访问
      </div>
      {payload.reasons && payload.reasons.length > 0 && (
        <div className="text-xs text-content-secondary pl-6">
          <span className="font-medium">原因:</span> {payload.reasons.join('；')}
        </div>
      )}
      {payload.risks && payload.risks.length > 0 && (
        <div className="text-xs text-status-warning pl-6">
          <span className="font-medium">风险:</span> {payload.risks.join('；')}
        </div>
      )}
    </div>
  )
})

const SandboxPathDetail = memo(function SandboxPathDetail({ payload }: { payload: SandboxPathPayload }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
        <FolderLock className="h-4 w-4 shrink-0 text-content-muted" />
        <code className="font-mono text-sm break-all">{payload.command}</code>
      </div>
      <div className="text-xs text-status-warning pl-6">
        沙箱阻止了路径访问: {payload.denied_paths.join(', ')}
      </div>
      {payload.reasons && payload.reasons.length > 0 && (
        <div className="text-xs text-content-secondary pl-6">
          <span className="font-medium">原因:</span> {payload.reasons.join('；')}
        </div>
      )}
      {payload.risks && payload.risks.length > 0 && (
        <div className="text-xs text-status-warning pl-6">
          <span className="font-medium">风险:</span> {payload.risks.join('；')}
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

      {(() => {
        const d = detail.data
        if (!d || typeof d !== 'object' || !('screenshot_path' in d)) return null
        const screenshotPath = typeof d.screenshot_path === 'string' ? d.screenshot_path : undefined
        if (!screenshotPath) return null
        const width = typeof d.width === 'number' ? d.width : undefined
        const height = typeof d.height === 'number' ? d.height : undefined
        return (
          <div className="mt-2">
            <img
              src={`/api/browser/screenshot?path=${encodeURIComponent(screenshotPath)}`}
              alt="Browser screenshot"
              className="max-w-sm rounded border border-edge cursor-pointer hover:opacity-80"
              onClick={() => window.open(`/api/browser/screenshot?path=${encodeURIComponent(screenshotPath)}`, '_blank')}
            />
            {width != null && height != null && (
              <p className="mt-1 text-xs text-content-tertiary">
                {width}x{height} — 点击查看原图
              </p>
            )}
          </div>
        )
      })()}
    </div>
  )
})

const ApprovalCard = memo(function ApprovalCard({
  details,
  onApprovalAction,
  isSubAgent,
}: {
  details: ActionReceiptDetail[]
  onApprovalAction: (action: ApprovalActionType, payload: ApprovalActionPayload) => void
  isSubAgent?: boolean
}) {
  const approvalDetails = useMemo(() =>
    details
      .filter((detail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } => (
        detail.status === 'waiting_for_approval' && hasApproval(detail)
      ))
      .map((detail) => {
        const payload = detail.data
        const isRecord = payload && typeof payload === 'object'
        const approvalKind = isRecord && 'approval_kind' in payload && typeof payload.approval_kind === 'string'
          ? payload.approval_kind
          : detail.approval?.shell ? 'shell_command' : undefined
        let sandboxNetwork: SandboxNetworkPayload | undefined
        let sandboxPath: SandboxPathPayload | undefined

        if (approvalKind === 'sandbox_network_elevation' && isRecord) {
          sandboxNetwork = {
            approval_kind: 'sandbox_network_elevation',
            command: typeof payload.command === 'string' ? payload.command : '',
            execution_mode: typeof payload.execution_mode === 'string' ? payload.execution_mode : '',
            reasons: Array.isArray(payload.reasons) ? payload.reasons.filter((r): r is string => typeof r === 'string') : [],
            risks: Array.isArray(payload.risks) ? payload.risks.filter((r): r is string => typeof r === 'string') : [],
          }
        } else if (approvalKind === 'sandbox_path_elevation' && isRecord) {
          const elevReq = 'elevation_request' in payload && typeof payload.elevation_request === 'object' && payload.elevation_request
            ? payload.elevation_request
            : undefined
          const deniedPaths = elevReq && 'denied_paths' in elevReq && Array.isArray(elevReq.denied_paths)
            ? elevReq.denied_paths.filter((p): p is string => typeof p === 'string')
            : []
          sandboxPath = {
            approval_kind: 'sandbox_path_elevation',
            command: typeof payload.command === 'string' ? payload.command : '',
            execution_mode: typeof payload.execution_mode === 'string' ? payload.execution_mode : '',
            denied_paths: deniedPaths,
            reasons: Array.isArray(payload.reasons) ? payload.reasons.filter((r): r is string => typeof r === 'string') : [],
            risks: Array.isArray(payload.risks) ? payload.risks.filter((r): r is string => typeof r === 'string') : [],
          }
        }

        return {
          id: detail.id,
          approval: detail.approval,
          shell: detail.approval.shell,
          sandboxNetwork,
          sandboxPath,
          approvalKind,
        }
      }),
    [details]
  )

  const summary = useMemo(() => summarizeReceipt(details, 'waiting_for_approval'), [details])

  return (
    <div className="mb-8 max-w-[920px] mx-auto w-full rounded-xl border border-edge bg-surface-primary overflow-hidden">
      <div className="flex flex-col gap-3 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-content-primary">
          <ShieldAlert className="h-4 w-4 shrink-0 text-content-muted" />
          <span>{isSubAgent ? '子代理需要批准执行命令' : '需要批准执行命令'}</span>
        </div>
        <p className="text-sm text-content-muted">{summary}</p>

        {approvalDetails.map((detail) => (
          <div key={detail.id} className="rounded-lg border border-edge bg-surface-secondary px-3 py-2">
            {detail.shell && <ShellApprovalDetail key="shell" shell={detail.shell} />}
            {detail.sandboxNetwork && <SandboxNetworkDetail key="network" payload={detail.sandboxNetwork} />}
            {detail.sandboxPath && <SandboxPathDetail key="path" payload={detail.sandboxPath} />}
          </div>
        ))}
      </div>

      <div className="border-t border-edge bg-surface-secondary px-4 py-3">
        {approvalDetails.map((detail) => {
          const isNetworkElevation = detail.approvalKind === 'sandbox_network_elevation'
          const isPathElevation = detail.approvalKind === 'sandbox_path_elevation'
          const allowLabel = isNetworkElevation ? '允许网络一次' : isPathElevation ? '允许访问一次' : '允许一次'
          const trustLabel = isNetworkElevation ? '此会话允许网络' : isPathElevation ? '此会话允许访问' : '此会话允许'

          return (
            <div key={detail.id} className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => sendApprovalAction(onApprovalAction, 'approve', detail.approval)}
                className="inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40"
              >
                <Check className="h-3.5 w-3.5" />
                {allowLabel}
              </button>
              <button
                type="button"
                onClick={() => sendApprovalAction(onApprovalAction, 'trust', detail.approval)}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-accent bg-surface-primary px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent/10 focus:outline-none focus:ring-2 focus:ring-accent/30"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                {trustLabel}
              </button>
              {detail.shell && detail.approval.suggestedTrust?.prefix && (
                <span className="text-xs text-content-muted">
                  将信任: {detail.approval.suggestedTrust.prefix.join(', ')}
                </span>
              )}
              {(isNetworkElevation || isPathElevation) && detail.approval.suggestedTrust && (
                <span className="text-xs text-content-muted">
                  {isNetworkElevation ? '将信任: 网络访问' : `将信任: ${detail.approval.suggestedTrust.pattern || ''}`}
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
          )
        })}
      </div>
    </div>
  )
})

export const ActionReceipt = memo(function ActionReceipt({ status, details, onApprovalAction, onDetailClick, isSubAgent }: ActionReceiptProps) {
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
    return <ApprovalCard details={details} onApprovalAction={onApprovalAction} isSubAgent={isSubAgent} />
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
