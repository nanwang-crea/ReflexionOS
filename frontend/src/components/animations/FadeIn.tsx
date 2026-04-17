import { motion } from 'framer-motion'
import { ReactNode } from 'react'
import { useAnimationStore } from '@/stores/animationStore'
import { durationMap } from '@/types/animation'

interface FadeInProps {
  children: ReactNode
  delay?: number
  className?: string
}

export function FadeIn({ children, delay = 0, className = '' }: FadeInProps) {
  const { duration, reducedMotion } = useAnimationStore()
  
  if (reducedMotion) {
    return <div className={className}>{children}</div>
  }
  
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ 
        duration: durationMap[duration], 
        delay 
      }}
    >
      {children}
    </motion.div>
  )
}
