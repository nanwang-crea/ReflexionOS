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

  return (
    <Router>
      <div className="flex h-screen bg-surface-primary">
        <WorkspaceSidebar />
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
