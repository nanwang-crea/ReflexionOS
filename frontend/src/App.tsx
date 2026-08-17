/**
 * 文件功能：应用根组件
 * 文件描述：定义整体页面骨架（侧边栏 + 路由主内容区），并挂载全局的 Toast、确认弹窗、右键菜单等宿主组件
 * 核心逻辑：通过 HashRouter 管理各功能页面（智能体工作区/技能/插件/自动化/设置）的路由切换；
 *          监听主题状态变化并应用到 DOM，侧边栏可折叠/展开
 */
import { useEffect } from 'react'
import { HashRouter as Router, Navigate, Route, Routes } from 'react-router-dom'
import AgentWorkspace from './pages/AgentWorkspace'
import SettingsPage from './pages/SettingsPage'
import SkillsPage from './pages/SkillsPage'
import PluginsPage from './pages/PluginsPage'
import AutomationPage from './pages/AutomationPage'
import { WorkspaceSidebar } from './components/layout/WorkspaceSidebar'
import { useThemeStore, applyTheme } from '@/shared/stores/theme.store'
import { ToastContainer } from '@/components/common/Toast'
import { ConfirmDialogHost } from '@/components/common/ConfirmDialog'
import { ContextMenuHost } from '@/components/common/ContextMenu'

/**
 * 函数名：useThemeEffect
 * 入参：无
 * 功能：将主题状态同步应用到页面 DOM，并在“跟随系统”模式下响应系统深浅色切换
 * 运行逻辑：
 *   1. 从主题 store 中读取当前主题（light/dark/system）
 *   2. 每次主题变化时调用 applyTheme 应用到 DOM
 *   3. 若为 system 模式，监听系统颜色方案变化（prefers-color-scheme），变化时重新应用主题
 *   4. 组件卸载或依赖变化时移除监听，避免内存泄漏
 * 出参：无（副作用型 hook，不返回值）
 */
function useThemeEffect() {
  const theme = useThemeStore((s) => s.theme)
  useEffect(() => {
    applyTheme(theme)
    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      const handler = () => applyTheme('system')
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    }
  }, [theme])
}

/**
 * 函数名：App
 * 入参：无（根组件，无 props）
 * 功能：渲染应用整体布局，包括可折叠侧边栏、路由主内容区，以及全局宿主组件
 * 运行逻辑：
 *   1. 调用 useThemeEffect 保持主题与 DOM 同步
 *   2. 从主题 store 读取侧边栏折叠状态，决定渲染完整侧边栏还是折叠后的展开按钮
 *   3. 使用 react-router-dom 的 Routes 定义各页面路径（默认重定向到 /agent）
 *   4. 渲染全局 Toast 容器、确认弹窗宿主、右键菜单宿主，供任意子组件调用
 * 出参：JSX.Element - 整个应用的根 DOM 结构
 */
function App() {
  useThemeEffect()
  const sidebarCollapsed = useThemeStore((s) => s.sidebarCollapsed)

  return (
    <Router>
      <div className="flex h-screen flex-col bg-surface-primary md:flex-row">
        {!sidebarCollapsed ? (
          <WorkspaceSidebar />
        ) : (
          <button
            type="button"
            onClick={() => useThemeStore.getState().toggleSidebar()}
            className="flex h-10 w-full shrink-0 items-center justify-center border-b border-edge bg-surface-secondary text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary md:h-full md:w-10 md:border-b-0 md:border-r"
            title="展开侧边栏"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/></svg>
          </button>
        )}
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface-primary">
          <Routes>
            <Route path="/" element={<Navigate to="/agent" replace />} />
            <Route path="/agent" element={<AgentWorkspace />} />
            <Route path="/skills" element={<SkillsPage />} />
            <Route path="/plugins" element={<PluginsPage />} />
            <Route path="/automation" element={<AutomationPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
      <ToastContainer />
      <ConfirmDialogHost />
      <ContextMenuHost />
    </Router>
  )
}

export default App
