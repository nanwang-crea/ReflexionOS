import { motion } from 'framer-motion'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'

type StepStatus = 'running' | 'success' | 'failed'

interface StatusBadgeProps {
  status: StepStatus
  size?: 'sm' | 'md' | 'lg'
}

const statusConfig = {
  running: {
    icon: Loader2,
    color: 'text-blue-500',
    bgColor: 'bg-blue-50',
    animate: { rotate: 360 }
  },
  success: {
    icon: CheckCircle2,
    color: 'text-green-500',
    bgColor: 'bg-green-50',
    animate: { scale: [0.8, 1] }
  },
  failed: {
    icon: XCircle,
    color: 'text-red-500',
    bgColor: 'bg-red-50',
    animate: { x: [0, -5, 5, -5, 5, 0] }
  }
}

const sizeConfig = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6'
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status]
  const Icon = config.icon
  
  return (
    <motion.div
      className={`flex items-center justify-center ${config.bgColor} rounded-full p-1`}
      initial={config.animate}
      animate={status === 'running' ? { rotate: 360 } : config.animate}
      transition={status === 'running' 
        ? { duration: 1, repeat: Infinity, ease: 'linear' }
        : { duration: 0.3 }
      }
    >
      <Icon className={`${config.color} ${sizeConfig[size]}`} />
    </motion.div>
  )
}
