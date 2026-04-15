import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom'
import ProjectsPage from './pages/ProjectsPage'
import AgentPage from './pages/AgentPage'
import SettingsPage from './pages/SettingsPage'

function App() {
  return (
    <Router>
      <div className="flex h-screen bg-gray-50">
        <nav className="w-64 bg-white border-r border-gray-200 p-4">
          <div className="mb-8">
            <h1 className="text-xl font-bold text-gray-900">ReflexionOS</h1>
            <p className="text-sm text-gray-500">AI Agent Workspace</p>
          </div>
          
          <ul className="space-y-2">
            <li>
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `block px-4 py-2 rounded-lg ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                Projects
              </NavLink>
            </li>
            <li>
              <NavLink
                to="/agent"
                className={({ isActive }) =>
                  `block px-4 py-2 rounded-lg ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                Agent
              </NavLink>
            </li>
            <li>
              <NavLink
                to="/settings"
                className={({ isActive }) =>
                  `block px-4 py-2 rounded-lg ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                Settings
              </NavLink>
            </li>
          </ul>
        </nav>

        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<ProjectsPage />} />
            <Route path="/agent" element={<AgentPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
