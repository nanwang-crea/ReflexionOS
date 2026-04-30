import { create } from 'zustand'
import type { AnimationConfig } from '@/types/animation'

interface AnimationState extends AnimationConfig {
  setReducedMotion: (reducedMotion: boolean) => void
}

export const useAnimationStore = create<AnimationState>((set) => ({
  duration: 'normal',
  reducedMotion: false,

  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
}))

if (typeof window !== 'undefined') {
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  useAnimationStore.getState().setReducedMotion(mediaQuery.matches)
  
  mediaQuery.addEventListener('change', (e) => {
    useAnimationStore.getState().setReducedMotion(e.matches)
  })
}
