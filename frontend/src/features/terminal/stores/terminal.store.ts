import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { terminalIpc } from '@/services/terminalIpc'

const MIN_PANEL_HEIGHT = 100
const MAX_PANEL_HEIGHT = 600
const DEFAULT_PANEL_HEIGHT = 280

export interface TerminalInstance {
  id: string
  title: string
  ptyPid: number | null
  exited: boolean
  cwd: string
}

interface TerminalState {
  instances: TerminalInstance[]
  activeTerminalId: string | null
  panelVisible: boolean
  panelHeight: number
}

interface TerminalActions {
  createTerminal: (cwd: string) => string
  closeTerminal: (id: string) => void
  closeAllTerminals: () => void
  setActiveTerminal: (id: string) => void
  setPtyPid: (id: string, pid: number) => void
  togglePanel: () => void
  setPanelVisible: (visible: boolean) => void
  setPanelHeight: (height: number) => void
  markExited: (id: string) => void
}

export let terminalCounter = 0

export function _resetForTesting() {
  terminalCounter = 0
  useTerminalStore.setState({
    instances: [],
    activeTerminalId: null,
    panelVisible: false,
    panelHeight: DEFAULT_PANEL_HEIGHT,
  })
}

export const useTerminalStore = create<TerminalState & TerminalActions>()(
  persist(
    (set) => ({
      instances: [],
      activeTerminalId: null,
      panelVisible: false,
      panelHeight: DEFAULT_PANEL_HEIGHT,

      createTerminal: (cwd: string) => {
        terminalCounter += 1
        const id = `term-${Date.now()}-${terminalCounter}`
        const instance: TerminalInstance = {
          id,
          title: `终端 ${terminalCounter}`,
          ptyPid: null,
          exited: false,
          cwd,
        }
        set((state) => ({
          instances: [...state.instances, instance],
          activeTerminalId: id,
          panelVisible: true,
        }))
        return id
      },

      closeTerminal: (id) => {
        terminalIpc.kill(id).catch(() => {})
        set((state) => {
          const remaining = state.instances.filter((t) => t.id !== id)
          let newActiveId = state.activeTerminalId
          if (newActiveId === id) {
            newActiveId = remaining.length > 0 ? remaining[remaining.length - 1].id : null
          }
          return {
            instances: remaining,
            activeTerminalId: newActiveId,
            panelVisible: remaining.length > 0 ? state.panelVisible : false,
          }
        })
      },

      closeAllTerminals: () => {
        const { instances } = useTerminalStore.getState()
        for (const inst of instances) {
          terminalIpc.kill(inst.id).catch(() => {})
        }
        set({ instances: [], activeTerminalId: null, panelVisible: false })
      },

      setActiveTerminal: (id) => set({ activeTerminalId: id }),

      setPtyPid: (id, pid) =>
        set((state) => ({
          instances: state.instances.map((t) =>
            t.id === id ? { ...t, ptyPid: pid } : t,
          ),
        })),

      togglePanel: () =>
        set((state) => ({ panelVisible: !state.panelVisible })),

      setPanelVisible: (visible) => set({ panelVisible: visible }),

      setPanelHeight: (height) =>
        set({
          panelHeight: Math.max(MIN_PANEL_HEIGHT, Math.min(MAX_PANEL_HEIGHT, height)),
        }),

      markExited: (id) =>
        set((state) => ({
          instances: state.instances.map((t) =>
            t.id === id ? { ...t, exited: true } : t,
          ),
        })),
    }),
    {
      name: 'reflexion-terminal',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        panelVisible: state.panelVisible,
        panelHeight: state.panelHeight,
      }),
    },
  ),
)
