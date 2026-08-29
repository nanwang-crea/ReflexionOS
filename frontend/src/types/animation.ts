// 文件功能：动画相关类型定义
// 文件描述：定义动画时长档位、动画配置项，以及档位到具体秒数的映射表，供全局动画/过渡效果统一取值
// 核心逻辑：通过“档位”而非具体数值来配置动画时长，实现统一调节与无障碍降级（reducedMotion）

// 动画时长档位：fast(快) / normal(正常) / slow(慢)，具体秒数见 durationMap
type AnimationDuration = 'fast' | 'normal' | 'slow'

// 动画配置项：duration 指定动画时长档位，reducedMotion 表示用户是否开启了“减弱动效”偏好（开启时应跳过或简化动画）
export interface AnimationConfig {
  duration: AnimationDuration
  reducedMotion: boolean
}

// 动画时长档位到具体秒数的映射表：fast=0.15s，normal=0.3s，slow=0.5s
export const durationMap: Record<AnimationDuration, number> = {
  fast: 0.15,
  normal: 0.3,
  slow: 0.5
}
