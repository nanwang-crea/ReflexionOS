import { motion } from 'framer-motion'
import { CheckCircle2 } from 'lucide-react'

interface SuccessToastProps {
  message: string
  duration?: number
  onDismiss?: () => void
}

export function SuccessToast({ message, duration = 3000, onDismiss }: SuccessToastProps) {
  return (
    <motion.div
      className="bg-green-50 border border-green-200 rounded-lg shadow-lg p-4"
      initial={{ opacity: 0, y: -20, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.9 }}
      transition={{ duration: 0.3, type: 'spring', stiffness: 300 }}
    >
      <div className="flex items-center gap-3">
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.1, type: 'spring', stiffness: 400 }}
        >
          <CheckCircle2 className="w-5 h-5 text-green-500" />
        </motion.div>
        <span className="text-green-800">{message}</span>
      </div>
    </motion.div>
  )
}
