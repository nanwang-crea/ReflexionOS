import { motion } from 'framer-motion'
import { ReactNode } from 'react'
import { useAnimationStore } from '@/stores/animationStore'
import { durationMap } from '@/types/animation'

interface SlideInProps {
  children: ReactNode
  direction?: 'up' | 'down' | 'left' | 'right'
  delay?: number
  className?: string
}

export function SlideIn({ 
  children, 
  direction = 'up', 
  delay = 0,
  className = '' 
}: SlideInProps) {
  const { duration, reducedMotion } = useAnimationStore()
  
  const directionOffset = {
    up: { y: 20 },
    down: { y: -20 },
    left: { x: 20 },
    right: { x: -20 }
  }
  
  if (reducedMotion) {
    return <div className={className}>{children}</div>
  }
  
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, ...directionOffset[direction] }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ 
        duration: durationMap[duration], 
        delay,
        ease: 'easeOut'
      }}
    >
      {children}
    </motion.div>
  )
}
