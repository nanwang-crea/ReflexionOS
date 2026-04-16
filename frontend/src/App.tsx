import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom'
import ProjectsPage from './pages/ProjectsPage'
import AgentWorkspace from './pages/AgentWorkspace'
import SettingsPage from './pages/SettingsPage'

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-gray-100">
        {/* Sidebar */}
        <nav className="w-64 bg-slate-900 text-white flex flex-col">
          <div className="p-6">
            <h1 className="text-xl font-bold">ReflexionOS</h1>
            <p className="text-sm text-slate-400 mt-1">AI Agent Workspace</p>
          </div>
          
          <ul className="flex-1 px-3 space-y-1">
            <li>
              <NavLink
                to="/agent"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`
                }
              >
                <span>💬</span>
                <span>Agent 对话</span>
              </NavLink>
            </li>
            <li>
              <NavLink
                to="/projects"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`
                }
              >
                <span>📁</span>
                <span>项目管理</span>
              </NavLink>
            </li>
            <li>
              <NavLink
                to="/settings"
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`
                }
              >
                <span>⚙️</span>
                <span>设置</span>
              </NavLink>
            </li>
          </ul>

          <div className="p-4 border-t border-slate-700">
            <p className="text-xs text-slate-500">v0.1.0 MVP</p>
          </div>
        </nav>

        {/* Main Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <Routes>
            <Route path="/" element={<AgentWorkspace />} />
            <Route path="/agent" element={<AgentWorkspace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
