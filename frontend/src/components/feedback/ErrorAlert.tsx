import { motion } from 'framer-motion'
import { AlertCircle, X } from 'lucide-react'

interface ErrorAlertProps {
  title?: string
  message: string
  onDismiss?: () => void
}

export function ErrorAlert({ title = '错误', message, onDismiss }: ErrorAlertProps) {
  return (
    <motion.div
      className="bg-red-50 border-2 border-red-200 rounded-lg p-4"
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-start gap-3">
        <motion.div
          animate={{ x: [0, -5, 5, -5, 5, 0] }}
          transition={{ duration: 0.4 }}
        >
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
        </motion.div>
        
        <div className="flex-1">
          <h4 className="font-medium text-red-800">{title}</h4>
          <p className="text-sm text-red-700 mt-1">{message}</p>
        </div>
        
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-red-400 hover:text-red-600 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </motion.div>
  )
}
