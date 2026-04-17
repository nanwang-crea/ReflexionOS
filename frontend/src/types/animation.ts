export type AnimationDuration = 'fast' | 'normal' | 'slow'

export interface AnimationConfig {
  duration: AnimationDuration
  reducedMotion: boolean
}

export const durationMap: Record<AnimationDuration, number> = {
  fast: 0.15,
  normal: 0.3,
  slow: 0.5
}
