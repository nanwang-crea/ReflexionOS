// 文件功能：全局动画配置状态（zustand store）
// 文件描述：维护动画时长档位与“是否降低动效”标志；后者跟随系统级
//           prefers-reduced-motion 媒体查询自动同步，供全局动画组件读取以决定是否精简/关闭动效
// 核心逻辑：store 创建后立即读取一次系统偏好写入初始状态，并注册 change 监听，
//           系统偏好变化时（如用户在系统设置中切换）自动更新 reducedMotion；
//           该副作用仅在浏览器环境（存在 window）下执行，避免在 SSR/测试等无 DOM 环境报错
import { create } from 'zustand'
import type { AnimationConfig } from '@/types/animation'

// AnimationState：动画配置状态 + 状态更新方法
interface AnimationState extends AnimationConfig {
  setReducedMotion: (reducedMotion: boolean) => void
}

// useAnimationStore：全局动画配置 store
// 初始 duration 固定为 'normal'，reducedMotion 初始为 false（随后由下方副作用同步系统偏好）
export const useAnimationStore = create<AnimationState>((set) => ({
  duration: 'normal',
  reducedMotion: false,

  /**
   * 函数名：setReducedMotion
   * 入参：
   *   - reducedMotion (boolean): 是否应降低/关闭动效
   * 功能：更新 store 中的 reducedMotion 状态
   * 运行逻辑：直接调用 zustand 的 set 写入新值
   * 出参：无
   */
  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
}))

// 以下为模块加载时执行的副作用：仅在浏览器环境下，
// 读取系统 prefers-reduced-motion 偏好并同步到 store，同时监听后续变化
if (typeof window !== 'undefined') {
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  useAnimationStore.getState().setReducedMotion(mediaQuery.matches)

  mediaQuery.addEventListener('change', (e) => {
    useAnimationStore.getState().setReducedMotion(e.matches)
  })
}
