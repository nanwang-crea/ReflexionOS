import { motion } from 'framer-motion'
import { Pause, Play, Square } from 'lucide-react'
import { useExecutionStore } from '@/stores/executionStore'

interface ExecutionControlsProps {
  onPause?: () => void
  onResume?: () => void
  onStop?: () => void
}

export function ExecutionControls({ onPause, onResume, onStop }: ExecutionControlsProps) {
  const { status, canPause, canStop } = useExecutionStore()
  
  if (status === 'idle' || status === 'stopped') {
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
      {status === 'running' && canPause && (
        <motion.button
          onClick={onPause}
          className="flex items-center gap-2 px-4 py-2 bg-yellow-500 text-white rounded-lg
                     hover:bg-yellow-600 shadow-lg shadow-yellow-500/30"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Pause className="w-4 h-4" />
          <span>暂停</span>
        </motion.button>
      )}
      
      {status === 'paused' && (
        <motion.button
          onClick={onResume}
          className="flex items-center gap-2 px-4 py-2 bg-green-500 text-white rounded-lg
                     hover:bg-green-600 shadow-lg shadow-green-500/30"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Play className="w-4 h-4" />
          <span>继续</span>
        </motion.button>
      )}
      
      {canStop && (
        <motion.button
          onClick={onStop}
          className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg
                     hover:bg-red-600 shadow-lg shadow-red-500/30"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          <Square className="w-4 h-4" />
          <span>停止</span>
        </motion.button>
      )}
    </motion.div>
  )
}
