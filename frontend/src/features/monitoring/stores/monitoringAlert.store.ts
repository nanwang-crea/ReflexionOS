import { create } from 'zustand'
import type { MonitoringAlertState } from '@/types/monitoring'

interface MonitoringAlertStoreState {
  activeAlerts: MonitoringAlertState[]
  lastFetchedAt: string | null
  setActiveAlerts: (alerts: MonitoringAlertState[]) => void
}

export const useMonitoringAlertStore = create<MonitoringAlertStoreState>((set) => ({
  activeAlerts: [],
  lastFetchedAt: null,
  setActiveAlerts: (alerts) => set({
    activeAlerts: alerts,
    lastFetchedAt: new Date().toISOString(),
  }),
}))
