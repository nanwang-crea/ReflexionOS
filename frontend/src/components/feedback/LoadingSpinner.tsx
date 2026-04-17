import { motion } from 'framer-motion'
import { Loader2 } from 'lucide-react'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  text?: string
}

const sizeMap = {
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-8 h-8'
}

export function LoadingSpinner({ size = 'md', text }: LoadingSpinnerProps) {
  return (
    <div className="flex items-center gap-2">
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      >
        <Loader2 className={`${sizeMap[size]} text-blue-500`} />
      </motion.div>
      {text && <span className="text-gray-600">{text}</span>}
    </div>
  )
}
