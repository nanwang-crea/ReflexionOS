import { useEffect } from 'react'
import { HashRouter as Router, Navigate, Route, Routes } from 'react-router-dom'
import AgentWorkspace from './pages/AgentWorkspace'
import SettingsPage from './pages/SettingsPage'
import SkillsPage from './pages/SkillsPage'
import PluginsPage from './pages/PluginsPage'
import AutomationPage from './pages/AutomationPage'
import { WorkspaceSidebar } from './components/layout/WorkspaceSidebar'
import { useThemeStore, applyTheme } from './stores/themeStore'

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

function App() {
  useThemeEffect()
  const sidebarCollapsed = useThemeStore((s) => s.sidebarCollapsed)

  return (
    <Router>
      <div className="flex h-screen bg-surface-primary">
        {!sidebarCollapsed ? (
          <WorkspaceSidebar />
        ) : (
          <button
            type="button"
            onClick={() => useThemeStore.getState().toggleSidebar()}
            className="flex h-full w-10 shrink-0 items-center justify-center border-r border-edge bg-surface-secondary text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary"
            title="展开侧边栏"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/></svg>
          </button>
        )}
        <main className="flex flex-1 flex-col overflow-hidden bg-surface-primary">
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
    </Router>
  )
}

export default App
