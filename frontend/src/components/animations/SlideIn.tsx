// 滑入动画容器组件：基于 framer-motion 实现子元素从指定方向滑入并淡入的过渡效果，
// 动画时长与是否启用取决于全局 animation.store（用户可配置动画速度、是否减少动效）。
import { motion } from 'framer-motion'
import { ReactNode } from 'react'
import { useAnimationStore } from '@/shared/stores/animation.store'
import { durationMap } from '@/types/animation'

interface SlideInProps {
  children: ReactNode
  direction?: 'up' | 'down' | 'left' | 'right'
  delay?: number
  className?: string
}

// 参数：children - 需要做滑入动效的子元素；direction - 滑入方向（默认 up，从下往上滑入）；
// delay - 动画延迟时间（秒，默认 0）；className - 外层容器的样式类名。
// 作用：根据全局动画配置计算动效时长；若用户开启了“减少动效”，则直接渲染子元素（跳过动画）；
// 否则用 framer-motion 实现从指定方向偏移、透明度 0 过渡到最终位置、透明度 1 的滑入效果。
// 返回：包裹 children 的 motion.div（或减少动效时的普通 motion.div）。
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
    return <motion.div className={className}>{children}</motion.div>
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
