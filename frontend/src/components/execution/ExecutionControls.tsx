import { motion } from 'framer-motion'
import { Loader2, Square } from 'lucide-react'
import { useExecutionStore } from '@/stores/executionStore'

interface ExecutionControlsProps {
  onCancel?: () => void
}

export function ExecutionControls({ onCancel }: ExecutionControlsProps) {
  const { status, canCancel } = useExecutionStore()
  
  if (status === 'idle' || status === 'completed' || status === 'failed' || status === 'cancelled') {
    return null
  }
  
  return (
    <motion.div
      className="flex items-center gap-2"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.2 }}
    >
      {status === 'running' && canCancel && (
        <motion.button
          onClick={onCancel}
          className="flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-white
                     shadow-lg shadow-red-500/30 hover:bg-red-600"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Square className="w-4 h-4" />
          <span>取消</span>
        </motion.button>
      )}

      {status === 'cancelling' && (
        <div className="flex items-center gap-2 rounded-lg bg-slate-100 px-4 py-2 text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>取消中</span>
        </div>
      )}
    </motion.div>
  )
}
