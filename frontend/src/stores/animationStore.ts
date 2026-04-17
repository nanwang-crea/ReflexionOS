import { create } from 'zustand'
import { AnimationConfig, AnimationDuration } from '@/types/animation'

interface AnimationState extends AnimationConfig {
  setDuration: (duration: AnimationDuration) => void
  setReducedMotion: (reducedMotion: boolean) => void
}

export const useAnimationStore = create<AnimationState>((set) => ({
  duration: 'normal',
  reducedMotion: false,
  
  setDuration: (duration) => set({ duration }),
  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
}))

if (typeof window !== 'undefined') {
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  useAnimationStore.getState().setReducedMotion(mediaQuery.matches)
  
  mediaQuery.addEventListener('change', (e) => {
    useAnimationStore.getState().setReducedMotion(e.matches)
  })
}
