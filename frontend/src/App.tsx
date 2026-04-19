import { HashRouter as Router, Navigate, Route, Routes } from 'react-router-dom'
import AgentWorkspace from './pages/AgentWorkspace'
import SettingsPage from './pages/SettingsPage'
import SkillsPage from './pages/SkillsPage'
import PluginsPage from './pages/PluginsPage'
import AutomationPage from './pages/AutomationPage'
import { WorkspaceSidebar } from './components/layout/WorkspaceSidebar'

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-white">
        <WorkspaceSidebar />
        <main className="flex flex-1 flex-col overflow-hidden bg-white">
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
