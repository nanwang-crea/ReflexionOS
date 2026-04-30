import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, ChevronRight, Loader2 } from 'lucide-react'
import { type ActionReceiptDetail, type ActionReceiptStatus, summarizeReceipt } from './receiptUtils'

interface ActionReceiptProps {
  status: ActionReceiptStatus
  details: ActionReceiptDetail[]
}

function trimOutput(value: string, maxLength = 800) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}\n...` : value
}

export function ActionReceipt({ status, details }: ActionReceiptProps) {
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

  return (
    <div className="mb-8 max-w-[920px]">
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
        {status === 'failed' && (
          <AlertCircle className="h-3.5 w-3.5" />
        )}
        {status === 'cancelled' && (
          <AlertCircle className="h-3.5 w-3.5" />
        )}
      </button>

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
                      detail.status === 'running' ? 'bg-blue-400' : 'bg-slate-300'
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
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
