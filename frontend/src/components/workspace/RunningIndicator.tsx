import { motion } from 'framer-motion'

type RunningIndicatorLayout = 'header' | 'inline'

interface RunningIndicatorProps {
  label: string
  layout?: RunningIndicatorLayout
  rootDataAttr?: string
  barDataAttr?: string
}

function buildDataAttr(name: string | undefined, value: string) {
  return name ? { [name]: value } : {}
}

export function RunningIndicator({
  label,
  layout = 'inline',
  rootDataAttr,
  barDataAttr,
}: RunningIndicatorProps) {
  const isHeader = layout === 'header'

  return (
    <div
      {...buildDataAttr(rootDataAttr, 'true')}
      className={
        isHeader
          ? 'border-b border-edge-subtle bg-accent/8 px-4 py-3'
          : 'mb-8 flex items-center gap-3 text-sm text-content-secondary'
      }
      aria-live="polite"
    >
      <div className={isHeader ? 'flex items-center gap-3' : 'contents'}>
        <div className="flex w-10 flex-col gap-1.5">
          {[1, 2, 3].map((index) => (
            <div
              key={index}
              {...buildDataAttr(barDataAttr, String(index))}
              className={
                'relative h-1 overflow-hidden rounded-full bg-accent/20 ring-1 ring-accent/20'
              }
            >
              <motion.div
                className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-accent via-status-success to-accent-hover shadow-[0_0_14px_rgba(59,130,246,0.45)]"
                initial={{ x: '-55%', scaleX: 0.55, opacity: 0.55 }}
                animate={{
                  x: ['-55%', '10%', '42%', '-55%'],
                  scaleX: [0.55, 1, 0.8, 0.55],
                  opacity: [0.65, 1, 0.9, 0.65],
                }}
                transition={{
                  duration: 1.35,
                  repeat: Infinity,
                  ease: 'easeInOut',
                  delay: (index - 1) * 0.16,
                }}
                style={{ width: `${52 + index * 12}%` }}
              />
            </div>
          ))}
        </div>
        <div className="min-w-0">
          {isHeader && (
            <div className="text-[11px] uppercase tracking-[0.08em] text-accent">
              运行中
            </div>
          )}
          <div className={isHeader ? 'text-sm font-medium text-content-primary' : 'font-medium text-content-primary'}>
            {label}
          </div>
        </div>
      </div>
    </div>
  )
}
