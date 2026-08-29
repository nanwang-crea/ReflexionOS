// 文件功能：全局主题（明/暗/跟随系统）与侧边栏折叠状态（zustand store）
// 文件描述：维护用户选择的主题模式与侧边栏折叠状态，并通过 zustand persist 中间件
//           持久化到 localStorage，跨会话保留用户偏好；同时提供 applyTheme 将解析后的
//           实际主题（light/dark）应用到 document 根元素的 class 上，驱动全局样式切换
// 核心逻辑：theme 存储的是用户的“意图”（light/dark/system），resolveTheme 负责将
//           'system' 解析为当前系统实际的明暗偏好（通过 prefers-color-scheme 媒体查询）；
//           applyTheme 是纯副作用函数，不由 store 自动触发，需要调用方（如根组件）在
//           主题变化时手动调用
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark' | 'system'

// ThemeState：主题与侧边栏状态 + 状态更新方法
interface ThemeState {
  theme: ThemeMode
  sidebarCollapsed: boolean
  setTheme: (theme: ThemeMode) => void
  toggleSidebar: () => void
}

/**
 * 函数名：getSystemTheme
 * 入参：无
 * 功能：读取操作系统/浏览器当前的明暗主题偏好
 * 运行逻辑：非浏览器环境（window 未定义，如 SSR/测试）时直接返回 'light' 兜底；
 *           浏览器环境下通过 prefers-color-scheme: dark 媒体查询判断
 * 出参：'light' | 'dark' - 系统当前的实际主题
 */
function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/**
 * 函数名：resolveTheme
 * 入参：
 *   - theme (ThemeMode): 用户选择的主题模式，可能是 'system'
 * 功能：将用户的主题意图解析为实际可用的明/暗主题
 * 运行逻辑：若为 'system' 则委托 getSystemTheme 读取系统偏好，否则原样返回（已经是 light/dark）
 * 出参：'light' | 'dark' - 解析后的实际主题
 */
function resolveTheme(theme: ThemeMode): 'light' | 'dark' {
  return theme === 'system' ? getSystemTheme() : theme
}

// useThemeStore：全局主题与侧边栏状态 store，使用 persist 中间件持久化到 localStorage
// storage key 为 'reflexion-theme'，仅持久化 theme 与 sidebarCollapsed 两个字段（partialize）
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'light',
      sidebarCollapsed: false,
      // 函数名：setTheme；入参：theme (ThemeMode) - 新的主题模式；
      // 功能：更新用户选择的主题模式；运行逻辑：直接写入 state；出参：无
      setTheme: (theme) => set({ theme }),
      // 函数名：toggleSidebar；入参：无；
      // 功能：切换侧边栏折叠/展开状态；运行逻辑：基于当前 state 取反 sidebarCollapsed；出参：无
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
    }),
    {
      name: 'reflexion-theme',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ theme: state.theme, sidebarCollapsed: state.sidebarCollapsed }),
    },
  ),
)

/**
 * 函数名：applyTheme
 * 入参：
 *   - theme (ThemeMode): 用户选择的主题模式（可能是 'system'）
 * 功能：将解析后的实际主题应用到页面根元素，驱动全局暗色/亮色样式
 * 运行逻辑：先通过 resolveTheme 解析出实际的 light/dark，再对
 *           document.documentElement 的 'dark' class 做 toggle（暗色时添加，亮色时移除）
 * 出参：无（直接产生 DOM 副作用）
 */
export function applyTheme(theme: ThemeMode) {
  const resolved = resolveTheme(theme)
  document.documentElement.classList.toggle('dark', resolved === 'dark')
}
