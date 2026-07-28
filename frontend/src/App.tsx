import { useEffect, useRef } from 'react'
import { HashRouter as Router, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AgentWorkspace from './pages/AgentWorkspace'
import SettingsPage from './pages/SettingsPage'
import SkillsPage from './pages/SkillsPage'
import PluginsPage from './pages/PluginsPage'
import AutomationPage from './pages/AutomationPage'
import MonitoringPage from './pages/MonitoringPage'
import { WorkspaceSidebar } from './components/layout/WorkspaceSidebar'
import { monitoringApi } from '@/features/monitoring/api/monitoring.api'
import { useMonitoringAlertStore } from '@/features/monitoring/stores/monitoringAlert.store'
import { useToastStore } from '@/shared/stores/toast.store'
import { useThemeStore, applyTheme } from '@/shared/stores/theme.store'
import { ToastContainer } from '@/components/common/Toast'

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

function MonitoringAlertWatcher() {
  const location = useLocation()
  const initializedRef = useRef(false)
  const previousKeysRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    let disposed = false
    let timer: number | null = null

    const poll = async () => {
      try {
        const response = await monitoringApi.alerts({ window_hours: 24 })
        if (disposed) {
          return
        }
        const alerts = response.data.active_alerts
        useMonitoringAlertStore.getState().setActiveAlerts(alerts)
        const notificationsEnabled = response.data.settings.enable_in_app_notifications
        const pollIntervalMs = response.data.settings.poll_interval_seconds * 1000

        const nextKeys = new Set(alerts.map((alert) => `${alert.key}:${alert.severity}`))
        if (!initializedRef.current) {
          initializedRef.current = true
          previousKeysRef.current = nextKeys
          if (
            notificationsEnabled
            && alerts.length > 0
            && !location.pathname.startsWith('/monitoring')
          ) {
            const criticalCount = alerts.filter((alert) => alert.severity === 'critical').length
            useToastStore.getState().addToast(
              criticalCount > 0 ? 'error' : 'warning',
              criticalCount > 0
                ? `监控发现 ${criticalCount} 个严重告警`
                : `监控发现 ${alerts.length} 个活动告警`,
              6000,
            )
          }
          if (!disposed) {
            timer = window.setTimeout(() => {
              void poll()
            }, pollIntervalMs)
          }
          return
        }

        const newlyTriggered = alerts.filter(
          (alert) => !previousKeysRef.current.has(`${alert.key}:${alert.severity}`),
        )
        previousKeysRef.current = nextKeys

        if (notificationsEnabled && !location.pathname.startsWith('/monitoring')) {
          for (const alert of newlyTriggered) {
            useToastStore.getState().addToast(
              alert.severity === 'critical' ? 'error' : 'warning',
              `${alert.title}: ${alert.current_value}/${alert.threshold_value}`,
              6000,
            )
          }
        }
        if (!disposed) {
          timer = window.setTimeout(() => {
            void poll()
          }, pollIntervalMs)
        }
      } catch (error) {
        console.error('Failed to poll monitoring alerts:', error)
        if (!disposed) {
          timer = window.setTimeout(() => {
            void poll()
          }, 60_000)
        }
      }
    }

    void poll()

    return () => {
      disposed = true
      if (timer !== null) {
        window.clearTimeout(timer)
      }
    }
  }, [location.pathname])

  return null
}

function App() {
  useThemeEffect()
  const sidebarCollapsed = useThemeStore((s) => s.sidebarCollapsed)

  return (
    <Router>
      <MonitoringAlertWatcher />
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
            <Route path="/monitoring" element={<MonitoringPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
      <ToastContainer />
    </Router>
  )
}

export default App
