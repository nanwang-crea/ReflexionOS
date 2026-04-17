import { motion } from 'framer-motion'

interface SkeletonProps {
  className?: string
  variant?: 'text' | 'rectangular' | 'circular'
  width?: string | number
  height?: string | number
}

export function Skeleton({ 
  className = '', 
  variant = 'rectangular',
  width,
  height 
}: SkeletonProps) {
  const variantClasses = {
    text: 'rounded',
    rectangular: 'rounded-lg',
    circular: 'rounded-full'
  }
  
  const style: React.CSSProperties = {
    width: width,
    height: height || (variant === 'text' ? '1rem' : undefined)
  }
  
  return (
    <motion.div
      className={`bg-gray-200 ${variantClasses[variant]} ${className}`}
      style={style}
      animate={{ opacity: [0.5, 1, 0.5] }}
      transition={{ 
        duration: 1.5, 
        repeat: Infinity,
        ease: 'easeInOut'
      }}
    />
  )
}

export function MessageSkeleton() {
  return (
    <div className="space-y-3 p-4 bg-white rounded-lg border border-gray-200">
      <Skeleton variant="text" width="60%" />
      <Skeleton variant="text" width="80%" />
      <Skeleton variant="text" width="40%" />
    </div>
  )
}

export function StepSkeleton() {
  return (
    <div className="p-3 bg-white rounded-lg border border-gray-200">
      <div className="flex items-center gap-3">
        <Skeleton variant="circular" width={24} height={24} />
        <Skeleton variant="text" width="30%" />
        <Skeleton variant="text" width="20%" className="ml-auto" />
      </div>
    </div>
  )
}
