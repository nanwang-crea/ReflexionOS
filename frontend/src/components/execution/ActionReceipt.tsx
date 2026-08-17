/**
 * 文件功能：动作回执（ActionReceipt）UI 组件
 * 文件描述：展示一次工具调用/命令执行的回执信息，包括折叠展开的详情列表、输出/错误展开、
 *          截图预览，以及等待审批时的审批卡片（允许一次/信任/拒绝按钮）
 * 核心逻辑：根据传入的 status 决定渲染形态——waiting_for_approval 且提供了 onApprovalAction 时渲染 ApprovalCard，
 *          其余状态渲染可折叠的回执列表；列表内按状态排序展示，并支持点击文件类详情跳转编辑器
 */
import { memo, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, AlertTriangle, Check, ChevronDown, ChevronRight, Clock3, FolderLock, Globe, Loader2, ShieldAlert, ShieldCheck, Terminal, X } from 'lucide-react'
import { type ApprovalActionHandler, type ApprovalActionPayload, type ApprovalActionType, sendApprovalAction } from './approvalActions'
import { buildApprovalDetailFromPayload, type ActionReceiptDetail, type ActionReceiptStatus, type SandboxNetworkPayload, type SandboxPathPayload, type ShellApprovalPayload, summarizeReceipt } from './receiptUtils'

interface ActionReceiptProps {
  status: ActionReceiptStatus
  details: ActionReceiptDetail[]
  onApprovalAction?: ApprovalActionHandler
  onDetailClick?: (detail: ActionReceiptDetail) => void
  /** 是否为子代理的审批，用于区分标题显示 */
  isSubAgent?: boolean
}

/**
 * 函数名：hasApproval
 * 入参：
 *   - detail (ActionReceiptDetail): 单条回执详情
 * 功能：类型谓词，判断详情是否携带审批信息
 * 运行逻辑：检查 detail.approval 是否非 undefined
 * 出参：boolean（类型谓词）- 是否携带 approval 字段
 */
function hasApproval(detail: ActionReceiptDetail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } {
  return detail.approval !== undefined
}

/**
 * 函数名：trimOutput
 * 入参：
 *   - value (string): 原始输出/错误文本
 *   - maxLength (number): 最大展示长度，默认 800
 * 功能：截断过长的输出文本，避免撑爆界面
 * 运行逻辑：超出 maxLength 则截断并追加省略号提示
 * 出参：string - 截断后的文本
 */
function trimOutput(value: string, maxLength = 800) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}\n...` : value
}

/**
 * 组件名：ShellApprovalDetail
 * 入参（props）：
 *   - shell (ShellApprovalPayload): 待审批的 shell 命令信息（命令、执行模式、原因、风险）
 * 作用/渲染逻辑：展示命令本体，以及可选的执行模式、原因列表、风险列表
 * 返回值：JSX.Element - 审批详情卡片中的 shell 命令展示区块
 */
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

/**
 * 组件名：SandboxNetworkDetail
 * 入参（props）：
 *   - payload (SandboxNetworkPayload): 沙箱网络越权审批信息（命令、原因、风险）
 * 作用/渲染逻辑：展示命令本体与“沙箱阻止了网络访问”提示，以及可选的原因/风险列表
 * 返回值：JSX.Element - 审批详情卡片中的网络越权展示区块
 */
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

/**
 * 组件名：SandboxPathDetail
 * 入参（props）：
 *   - payload (SandboxPathPayload): 沙箱路径越权审批信息（命令、被拒绝路径、原因、风险）
 * 作用/渲染逻辑：展示命令本体与被拒绝的路径列表，以及可选的原因/风险列表
 * 返回值：JSX.Element - 审批详情卡片中的路径越权展示区块
 */
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

// 详情列表排序权重：失败/取消/运行中/等待审批的条目优先展示在前面，成功/待处理靠后
const DETAIL_STATUS_ORDER: Record<string, number> = {
  failed: 0,
  cancelled: 1,
  running: 2,
  waiting_for_approval: 3,
  success: 4,
  pending: 5,
}

/**
 * 组件名：ActionReceiptDetailRow
 * 入参（props）：
 *   - detail (ActionReceiptDetail): 单条回执详情数据
 *   - onDetailClick ((detail) => void，可选): 点击详情行时的回调（仅文件类 edit/create/delete 详情可点击）
 * 作用/渲染逻辑：
 *   展示单行详情摘要（状态点、summary 文本、耗时），并支持展开/收起输出与错误文本；
 *   若详情携带截图路径（screenshot_path）则额外渲染截图预览，可点击查看原图
 * 返回值：JSX.Element - 一行可展开的回执详情
 */
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

/**
 * 组件名：ApprovalCard
 * 入参（props）：
 *   - details (ActionReceiptDetail[]): 回执详情数组，组件内部会筛出处于 waiting_for_approval 且携带审批信息的项
 *   - onApprovalAction ((action, payload) => void): 用户点击“允许/信任/拒绝”按钮时的回调
 *   - isSubAgent (boolean，可选): 是否为子代理发起的审批，用于区分标题文案
 * 作用/渲染逻辑：
 *   1. 从 details 中筛选出等待审批的条目，解析出 shell/sandboxNetwork/sandboxPath 三种审批类型
 *   2. 顶部展示标题与摘要文案，中部展示每条待审批详情（命令、原因、风险等）
 *   3. 底部为每条待审批详情渲染“允许一次/此会话允许/拒绝”三个操作按钮，按审批类型调整按钮文案
 * 返回值：JSX.Element - 完整的审批卡片
 */
const ApprovalCard = memo(function ApprovalCard({
  details,
  onApprovalAction,
  isSubAgent,
}: {
  details: ActionReceiptDetail[]
  onApprovalAction: (action: ApprovalActionType, payload: ApprovalActionPayload) => void
  isSubAgent?: boolean
}) {
  const approvalDetails = useMemo(
    () =>
      details
        .filter((detail): detail is ActionReceiptDetail & { approval: ApprovalActionPayload } => (
          detail.status === 'waiting_for_approval' && hasApproval(detail)
        ))
        .map((detail) => {
          const payload = detail.data && typeof detail.data === 'object'
            ? detail.data
            : undefined
          const built = payload ? buildApprovalDetailFromPayload(payload) : undefined
          const approval = built?.approval ?? detail.approval
          const approvalKind = approval?.sandboxNetwork
            ? 'sandbox_network_elevation'
            : approval?.sandboxPath
              ? 'sandbox_path_elevation'
              : 'shell_command'

          return {
            id: detail.id,
            approval,
            shell: approval?.shell,
            sandboxNetwork: approval?.sandboxNetwork,
            sandboxPath: approval?.sandboxPath,
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

/**
 * 组件名：ActionReceipt
 * 入参（props，ActionReceiptProps）：
 *   - status (ActionReceiptStatus): 回执整体状态（运行中/等待审批/完成/部分失败/失败/取消）
 *   - details (ActionReceiptDetail[]): 本次回执包含的详情列表
 *   - onApprovalAction (ApprovalActionHandler，可选): 审批操作回调，提供且状态为等待审批时渲染审批卡片
 *   - onDetailClick ((detail) => void，可选): 点击详情行（文件类）时的回调，通常用于跳转到编辑器/差异视图
 *   - isSubAgent (boolean，可选): 是否为子代理的回执/审批，用于标题文案区分
 * 作用/渲染逻辑：
 *   1. 若状态为等待审批且提供了 onApprovalAction，直接渲染 ApprovalCard 处理审批交互
 *   2. 否则渲染一个可折叠的标题行（label 为单条摘要或汇总摘要），点击展开后按状态排序展示详情列表
 *   3. 展开区域底部提供“收起”按钮，收起后自动将标题行滚动到可视区域
 * 返回值：JSX.Element - 完整的动作回执组件（审批卡片或可折叠详情列表）
 */
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
