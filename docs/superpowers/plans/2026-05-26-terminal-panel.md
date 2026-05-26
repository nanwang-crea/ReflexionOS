# Terminal Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resizable, hideable terminal panel at the bottom of the code mode workspace, powered by xterm.js + node-pty over Electron IPC, with multi-instance tab support.

**Architecture:** Terminal panel lives at the AgentWorkspace level (below CodeTab). PTY processes are managed in Electron main process via IPC. A Zustand store manages terminal state. xterm.js renders in the renderer process.

**Tech Stack:** @xterm/xterm, @xterm/addon-fit, node-pty, Electron IPC, Zustand, React, TailwindCSS

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `frontend/src/features/terminal/terminalStore.ts` | Zustand store for terminal instances, panel visibility, height |
| Create | `frontend/src/components/terminal/TerminalPanel.tsx` | Panel container with drag bar and height control |
| Create | `frontend/src/components/terminal/TerminalInstance.tsx` | Single xterm.js instance lifecycle and data binding |
| Create | `frontend/src/components/terminal/TerminalTabBar.tsx` | Tab bar for switching/creating/closing terminals |
| Create | `frontend/src/services/terminalIpc.ts` | Typed IPC wrapper for terminal operations |
| Modify | `frontend/electron/preload.cjs` | Expose terminal IPC API to renderer |
| Modify | `frontend/electron/main.cjs` | Add terminal IPC handlers, manage PTY processes |
| Modify | `frontend/src/pages/AgentWorkspace.tsx` | Add TerminalPanel to code mode layout |
| Modify | `frontend/package.json` | Add @xterm/xterm, @xterm/addon-fit, node-pty |
| Create | `frontend/src/features/terminal/terminalStore.test.ts` | Tests for terminal store |

---

### Task 1: Install dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install xterm and node-pty packages**

Run:
```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && pnpm add @xterm/xterm @xterm/addon-fit node-pty
```

- [ ] **Step 2: Verify installation**

Run:
```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && pnpm ls @xterm/xterm @xterm/addon-fit node-pty
```
Expected: All three packages listed with versions

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml
git commit -m "chore: add xterm.js and node-pty dependencies"
```

---

### Task 2: Terminal store

**Files:**
- Create: `frontend/src/features/terminal/terminalStore.ts`
- Create: `frontend/src/features/terminal/terminalStore.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/features/terminal/terminalStore.test.ts
import { describe, expect, it } from 'vitest'
import { useTerminalStore } from './terminalStore'

describe('terminalStore', () => {
  it('should initialize with no terminals and panel hidden', () => {
    const state = useTerminalStore.getState()
    expect(state.instances).toEqual([])
    expect(state.activeTerminalId).toBeNull()
    expect(state.panelVisible).toBe(false)
    expect(state.panelHeight).toBe(200)
  })

  it('should create a terminal instance', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(1)
    expect(state.instances[0].title).toBe('终端 1')
    expect(state.activeTerminalId).toBe(state.instances[0].id)
    expect(state.panelVisible).toBe(true)
    useTerminalStore.getState().closeTerminal(state.instances[0].id)
  })

  it('should create multiple terminals with sequential titles', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(2)
    expect(state.instances[0].title).toBe('终端 1')
    expect(state.instances[1].title).toBe('终端 2')
    expect(state.activeTerminalId).toBe(state.instances[1].id)
    state.instances.forEach((t) => useTerminalStore.getState().closeTerminal(t.id))
  })

  it('should close a terminal and update active terminal', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    const firstId = instances[0].id
    const secondId = instances[1].id
    useTerminalStore.getState().closeTerminal(firstId)
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(1)
    expect(state.instances[0].id).toBe(secondId)
    expect(state.activeTerminalId).toBe(secondId)
    useTerminalStore.getState().closeTerminal(secondId)
  })

  it('should close last terminal and hide panel', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    useTerminalStore.getState().closeTerminal(instances[0].id)
    const state = useTerminalStore.getState()
    expect(state.instances).toHaveLength(0)
    expect(state.panelVisible).toBe(false)
  })

  it('should toggle panel visibility', () => {
    useTerminalStore.getState().togglePanel()
    expect(useTerminalStore.getState().panelVisible).toBe(true)
    useTerminalStore.getState().togglePanel()
    expect(useTerminalStore.getState().panelVisible).toBe(false)
  })

  it('should set panel height within bounds', () => {
    useTerminalStore.getState().setPanelHeight(300)
    expect(useTerminalStore.getState().panelHeight).toBe(300)
    useTerminalStore.getState().setPanelHeight(50)
    expect(useTerminalStore.getState().panelHeight).toBe(100)
    useTerminalStore.getState().setPanelHeight(9999)
    expect(useTerminalStore.getState().panelHeight).toBe(600)
  })

  it('should set active terminal', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    useTerminalStore.getState().setActiveTerminal(instances[0].id)
    expect(useTerminalStore.getState().activeTerminalId).toBe(instances[0].id)
    instances.forEach((t) => useTerminalStore.getState().closeTerminal(t.id))
  })

  it('should mark terminal as exited', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    const { instances } = useTerminalStore.getState()
    useTerminalStore.getState().markExited(instances[0].id)
    expect(useTerminalStore.getState().instances[0].exited).toBe(true)
    useTerminalStore.getState().closeTerminal(instances[0].id)
  })

  it('should close all terminals', () => {
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().createTerminal('/test/project')
    useTerminalStore.getState().closeAllTerminals()
    expect(useTerminalStore.getState().instances).toHaveLength(0)
    expect(useTerminalStore.getState().activeTerminalId).toBeNull()
    expect(useTerminalStore.getState().panelVisible).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && pnpm test -- src/features/terminal/terminalStore.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Write the store implementation**

```typescript
// frontend/src/features/terminal/terminalStore.ts
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

const MIN_PANEL_HEIGHT = 100
const MAX_PANEL_HEIGHT = 600
const DEFAULT_PANEL_HEIGHT = 200

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

let terminalCounter = 0

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

      closeTerminal: (id) =>
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
        }),

      closeAllTerminals: () =>
        set({ instances: [], activeTerminalId: null, panelVisible: false }),

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && pnpm test -- src/features/terminal/terminalStore.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/terminal/terminalStore.ts frontend/src/features/terminal/terminalStore.test.ts
git commit -m "feat: add terminal store with multi-instance and panel state"
```

---

### Task 3: Electron main process — PTY management and IPC handlers

**Files:**
- Modify: `frontend/electron/main.cjs`

- [ ] **Step 1: Add terminal IPC handlers to main.cjs**

At the top of `frontend/electron/main.cjs`, add the `node-pty` require after the existing requires:

```javascript
const os = require('os')
const pty = require('node-pty')
```

Add a `terminals` Map and IPC handlers before the `app.whenReady().then(bootstrap)` line:

```javascript
const terminals = new Map()

function getShellCommand() {
  if (process.platform === 'win32') {
    return 'cmd.exe'
  }
  return process.env.SHELL || '/bin/zsh'
}

ipcMain.handle('terminal:create', (_event, id, cwd) => {
  const shell = getShellCommand()
  const args = process.platform === 'darwin' ? ['--login'] : []
  const ptyProcess = pty.spawn(shell, args, {
    name: 'xterm-256color',
    cols: 80,
    rows: 24,
    cwd: cwd || os.homedir(),
    env: process.env as Record<string, string>,
  })

  terminals.set(id, ptyProcess)

  ptyProcess.onData((data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('terminal:data', id, data)
    }
  })

  ptyProcess.onExit(({ exitCode }) => {
    terminals.delete(id)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('terminal:exit', id, exitCode)
    }
  })

  return { pid: ptyProcess.pid }
})

ipcMain.handle('terminal:write', (_event, id, data) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.write(data)
  }
})

ipcMain.handle('terminal:resize', (_event, id, cols, rows) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.resize(cols, rows)
  }
})

ipcMain.handle('terminal:kill', (_event, id) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.kill()
    terminals.delete(id)
  }
})
```

In the existing `app.on('before-quit', ...)` handler, add PTY cleanup before `void backendManager.stop()`:

```javascript
for (const [, ptyProcess] of terminals) {
  try { ptyProcess.kill() } catch {}
}
terminals.clear()
```

- [ ] **Step 2: Verify the file parses correctly**

Run: `node -c /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/electron/main.cjs`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add frontend/electron/main.cjs
git commit -m "feat: add PTY management and terminal IPC handlers in main process"
```

---

### Task 4: Preload — expose terminal API

**Files:**
- Modify: `frontend/electron/preload.cjs`

- [ ] **Step 1: Add terminal API to preload**

Replace the entire content of `frontend/electron/preload.cjs` with:

```javascript
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  selectDirectory: () => ipcRenderer.invoke('dialog:select-directory'),
  getBackendStatus: () => ipcRenderer.invoke('backend:get-status'),
  terminal: {
    create: (id, cwd) => ipcRenderer.invoke('terminal:create', id, cwd),
    write: (id, data) => ipcRenderer.invoke('terminal:write', id, data),
    resize: (id, cols, rows) => ipcRenderer.invoke('terminal:resize', id, cols, rows),
    kill: (id) => ipcRenderer.invoke('terminal:kill', id),
    onData: (callback) => {
      const handler = (_event, id, data) => callback(id, data)
      ipcRenderer.on('terminal:data', handler)
      return () => ipcRenderer.removeListener('terminal:data', handler)
    },
    onExit: (callback) => {
      const handler = (_event, id, exitCode) => callback(id, exitCode)
      ipcRenderer.on('terminal:exit', handler)
      return () => ipcRenderer.removeListener('terminal:exit', handler)
    },
  },
})
```

- [ ] **Step 2: Verify syntax**

Run: `node -c /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend/electron/preload.cjs`
Expected: No syntax errors

- [ ] **Step 3: Commit**

```bash
git add frontend/electron/preload.cjs
git commit -m "feat: expose terminal IPC API in preload"
```

---

### Task 5: Renderer IPC service

**Files:**
- Create: `frontend/src/services/terminalIpc.ts`

- [ ] **Step 1: Create typed terminal IPC wrapper**

```typescript
// frontend/src/services/terminalIpc.ts
import { isElectronRuntime } from './desktopClient'

function getApi() {
  if (!isElectronRuntime()) {
    return null
  }
  return window.electronAPI?.terminal ?? null
}

export const terminalIpc = {
  isAvailable(): boolean {
    return getApi() !== null
  },

  async create(id: string, cwd: string): Promise<{ pid: number }> {
    const api = getApi()
    if (!api) throw new Error('Terminal IPC not available')
    return api.create(id, cwd)
  },

  async write(id: string, data: string): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.write(id, data)
  },

  async resize(id: string, cols: number, rows: number): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.resize(id, cols, rows)
  },

  async kill(id: string): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.kill(id)
  },

  onData(callback: (id: string, data: string) => void): () => void {
    const api = getApi()
    if (!api) return () => {}
    return api.onData(callback)
  },

  onExit(callback: (id: string, exitCode: number) => void): () => void {
    const api = getApi()
    if (!api) return () => {}
    return api.onExit(callback)
  },
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/terminalIpc.ts
git commit -m "feat: add typed terminal IPC service for renderer process"
```

---

### Task 6: TerminalTabBar component

**Files:**
- Create: `frontend/src/components/terminal/TerminalTabBar.tsx`

- [ ] **Step 1: Create TerminalTabBar**

```tsx
// frontend/src/components/terminal/TerminalTabBar.tsx
import { Plus, X } from 'lucide-react'
import { useTerminalStore } from '@/features/terminal/terminalStore'

interface TerminalTabBarProps {
  onClosePanel: () => void
}

export function TerminalTabBar({ onClosePanel }: TerminalTabBarProps) {
  const instances = useTerminalStore((s) => s.instances)
  const activeTerminalId = useTerminalStore((s) => s.activeTerminalId)
  const setActiveTerminal = useTerminalStore((s) => s.setActiveTerminal)
  const closeTerminal = useTerminalStore((s) => s.closeTerminal)
  const createTerminal = useTerminalStore((s) => s.createTerminal)
  const panelHeight = useTerminalStore((s) => s.panelHeight)

  const handleNew = () => {
    const cwd = instances.length > 0 ? instances[0].cwd : ''
    createTerminal(cwd)
  }

  return (
    <div className="flex items-center justify-between bg-[#16213e] px-2 py-1">
      <div className="flex items-center gap-1 overflow-x-auto">
        {instances.map((inst) => (
          <div
            key={inst.id}
            className={`group flex items-center gap-1 rounded px-2 py-0.5 text-xs cursor-pointer whitespace-nowrap ${
              inst.id === activeTerminalId
                ? 'bg-[#0f3460] text-white'
                : 'text-slate-400 hover:text-slate-200'
            } ${inst.exited ? 'opacity-50' : ''}`}
            onClick={() => setActiveTerminal(inst.id)}
          >
            <span>{inst.title}{inst.exited ? ' (已退出)' : ''}</span>
            <button
              type="button"
              className="hidden group-hover:inline-flex text-slate-400 hover:text-white"
              onClick={(e) => {
                e.stopPropagation()
                closeTerminal(inst.id)
              }}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        <button
          type="button"
          className="rounded p-0.5 text-slate-400 hover:text-slate-200"
          onClick={handleNew}
          title="新建终端"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <button
        type="button"
        className="rounded p-0.5 text-slate-400 hover:text-slate-200"
        onClick={onClosePanel}
        title="关闭面板"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/terminal/TerminalTabBar.tsx
git commit -m "feat: add TerminalTabBar component"
```

---

### Task 7: TerminalInstance component

**Files:**
- Create: `frontend/src/components/terminal/TerminalInstance.tsx`

- [ ] **Step 1: Create TerminalInstance**

```tsx
// frontend/src/components/terminal/TerminalInstance.tsx
import { useEffect, useRef, useCallback } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { useTerminalStore } from '@/features/terminal/terminalStore'
import { terminalIpc } from '@/services/terminalIpc'
import '@xterm/xterm/css/xterm.css'

interface TerminalInstanceProps {
  terminalId: string
}

export function TerminalInstance({ terminalId }: TerminalInstanceProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const setPtyPid = useTerminalStore((s) => s.setPtyPid)
  const markExited = useTerminalStore((s) => s.markExited)
  const cwd = useTerminalStore(
    (s) => s.instances.find((t) => t.id === terminalId)?.cwd ?? '',
  )

  const handleResize = useCallback(() => {
    if (fitAddonRef.current && termRef.current) {
      try {
        fitAddonRef.current.fit()
        const { cols, rows } = termRef.current
        terminalIpc.resize(terminalId, cols, rows)
      } catch {}
    }
  }, [terminalId])

  useEffect(() => {
    if (!containerRef.current) return

    const term = new Terminal({
      theme: {
        background: '#1a1a2e',
        foreground: '#0f0',
        cursor: '#0f0',
        selectionBackground: '#0f3460',
        black: '#1a1a2e',
        red: '#e74c3c',
        green: '#0f0',
        yellow: '#f1c40f',
        blue: '#3498db',
        magenta: '#9b59b6',
        cyan: '#1abc9c',
        white: '#ecf0f1',
        brightBlack: '#7f8c8d',
        brightRed: '#e74c3c',
        brightGreen: '#2ecc71',
        brightYellow: '#f1c40f',
        brightBlue: '#3498db',
        brightMagenta: '#9b59b6',
        brightCyan: '#1abc9c',
        brightWhite: '#ecf0f1',
      },
      fontSize: 13,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      cursorBlink: true,
      scrollback: 5000,
    })

    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    term.open(containerRef.current)
    fitAddon.fit()

    termRef.current = term
    fitAddonRef.current = fitAddon

    const unsubData = terminalIpc.onData((id, data) => {
      if (id === terminalId) {
        term.write(data)
      }
    })

    const unsubExit = terminalIpc.onExit((id) => {
      if (id === terminalId) {
        term.writeln('\r\n\x1b[33m进程已退出\x1b[0m')
        markExited(terminalId)
      }
    })

    term.onData((data) => {
      terminalIpc.write(terminalId, data)
    })

    terminalIpc.create(terminalId, cwd).then(({ pid }) => {
      setPtyPid(terminalId, pid)
    }).catch((err) => {
      term.writeln(`\x1b[31m终端创建失败: ${err.message}\x1b[0m`)
    })

    const resizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      unsubData()
      unsubExit()
      terminalIpc.kill(terminalId)
      term.dispose()
      termRef.current = null
      fitAddonRef.current = null
    }
  }, [terminalId])

  return (
    <div ref={containerRef} className="h-full w-full" />
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/terminal/TerminalInstance.tsx
git commit -m "feat: add TerminalInstance component with xterm.js lifecycle"
```

---

### Task 8: TerminalPanel component

**Files:**
- Create: `frontend/src/components/terminal/TerminalPanel.tsx`

- [ ] **Step 1: Create TerminalPanel**

```tsx
// frontend/src/components/terminal/TerminalPanel.tsx
import { useCallback, useRef } from 'react'
import { useTerminalStore } from '@/features/terminal/terminalStore'
import { TerminalTabBar } from './TerminalTabBar'
import { TerminalInstance } from './TerminalInstance'

export function TerminalPanel() {
  const instances = useTerminalStore((s) => s.instances)
  const activeTerminalId = useTerminalStore((s) => s.activeTerminalId)
  const panelVisible = useTerminalStore((s) => s.panelVisible)
  const panelHeight = useTerminalStore((s) => s.panelHeight)
  const togglePanel = useTerminalStore((s) => s.togglePanel)
  const setPanelHeight = useTerminalStore((s) => s.setPanelHeight)

  const isDragging = useRef(false)
  const dragStartY = useRef(0)
  const dragStartHeight = useRef(0)

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      isDragging.current = true
      dragStartY.current = e.clientY
      dragStartHeight.current = panelHeight

      const handleMouseMove = (moveEvent: MouseEvent) => {
        if (!isDragging.current) return
        const delta = dragStartY.current - moveEvent.clientY
        const newHeight = dragStartHeight.current + delta
        setPanelHeight(newHeight)
      }

      const handleMouseUp = () => {
        isDragging.current = false
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
      }

      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    },
    [panelHeight, setPanelHeight],
  )

  if (!panelVisible) return null

  const activeInstance = instances.find((t) => t.id === activeTerminalId)

  return (
    <div style={{ height: panelHeight }} className="flex flex-col flex-shrink-0">
      <div
        className="h-1 bg-blue-500 cursor-row-resize hover:h-1.5 transition-all flex-shrink-0"
        onMouseDown={handleMouseDown}
      />
      <TerminalTabBar onClosePanel={togglePanel} />
      <div className="flex-1 overflow-hidden bg-[#1a1a2e]">
        {activeInstance ? (
          <TerminalInstance key={activeInstance.id} terminalId={activeInstance.id} />
        ) : (
          <div className="flex h-full items-center justify-center text-slate-500 text-sm">
            没有活动的终端
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/terminal/TerminalPanel.tsx
git commit -m "feat: add TerminalPanel with drag-to-resize and visibility toggle"
```

---

### Task 9: Integrate TerminalPanel into AgentWorkspace

**Files:**
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **Step 1: Add TerminalPanel import and render**

Add import at the top of `AgentWorkspace.tsx`:

```typescript
import { TerminalPanel } from '@/components/terminal/TerminalPanel'
```

Replace the code mode section. Change this block:

```tsx
        {workspaceTab === 'code' ? (
          <CodeTab />
        ) : (
```

To:

```tsx
        {workspaceTab === 'code' ? (
          <>
            <div className="flex-1 min-h-0 overflow-hidden">
              <CodeTab />
            </div>
            <TerminalPanel />
          </>
        ) : (
```

This wraps CodeTab in a flex-1 container so it shares vertical space with the TerminalPanel, and renders the TerminalPanel below it.

- [ ] **Step 2: Verify no TypeScript errors**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit`
Expected: No errors related to AgentWorkspace, TerminalPanel

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: integrate TerminalPanel into AgentWorkspace code mode"
```

---

### Task 10: Add keyboard shortcuts

**Files:**
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **Step 1: Add keyboard shortcut handler**

Add `useEffect` import to `AgentWorkspace.tsx` (it already has `useCallback`, `useState` — add `useEffect`).

Add these imports:

```typescript
import { useTerminalStore } from '@/features/terminal/terminalStore'
import { useProjectStore } from '@/stores/projectStore'
```

Note: `useProjectStore` is already imported. Just add `useTerminalStore`.

Add a `useEffect` after the existing `workspaceTab` / `setActiveFile` hooks:

```tsx
  const togglePanel = useTerminalStore((s) => s.togglePanel)
  const createTerminal = useTerminalStore((s) => s.createTerminal)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '`' && e.ctrlKey && !e.shiftKey) {
        e.preventDefault()
        togglePanel()
      }
      if (e.key === '`' && e.ctrlKey && e.shiftKey) {
        e.preventDefault()
        const cwd = currentProject?.path ?? ''
        createTerminal(cwd)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [togglePanel, createTerminal, currentProject])
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: add Ctrl+` and Ctrl+Shift+` keyboard shortcuts for terminal"
```

---

### Task 11: Add terminal toggle button to WorkspaceHeader

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceHeader.tsx`

- [ ] **Step 1: Add terminal toggle button in code mode**

Add import:

```typescript
import { TerminalSquare } from 'lucide-react'
import { useTerminalStore } from '@/features/terminal/terminalStore'
```

Inside the `WorkspaceHeader` component, add:

```tsx
  const panelVisible = useTerminalStore((s) => s.panelVisible)
  const togglePanel = useTerminalStore((s) => s.togglePanel)
```

Add a terminal toggle button after the sidebar toggle button (inside the same `<div className="flex items-center gap-3">`). Only show it when in code mode:

```tsx
        {workspaceTab === 'code' && (
          <button
            type="button"
            onClick={togglePanel}
            className={`rounded-md p-1.5 transition-colors ${
              panelVisible
                ? 'text-slate-700 bg-slate-100'
                : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600'
            }`}
            title={panelVisible ? '隐藏终端' : '显示终端'}
          >
            <TerminalSquare className="h-4 w-4" />
          </button>
        )}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/WorkspaceHeader.tsx
git commit -m "feat: add terminal toggle button to WorkspaceHeader in code mode"
```

---

### Task 12: Add global type declaration for electronAPI.terminal

**Files:**
- Create or modify: `frontend/src/types/electron.d.ts`

- [ ] **Step 1: Check if electron.d.ts already exists**

If not, create it. Either way, ensure it contains the terminal type declarations:

```typescript
// frontend/src/types/electron.d.ts
export {}

declare global {
  interface Window {
    electronAPI?: {
      isElectron: boolean
      selectDirectory: () => Promise<string | null>
      getBackendStatus: () => Promise<{ state: string; url: string; pid: number | null; managed: boolean; error: string | null }>
      terminal: {
        create: (id: string, cwd: string) => Promise<{ pid: number }>
        write: (id: string, data: string) => Promise<void>
        resize: (id: string, cols: number, rows: number) => Promise<void>
        kill: (id: string) => Promise<void>
        onData: (callback: (id: string, data: string) => void) => () => void
        onExit: (callback: (id: string, exitCode: number) => void) => () => void
      }
    }
  }
}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/electron.d.ts
git commit -m "feat: add TypeScript declarations for electronAPI.terminal"
```

---

### Task 13: Run full test suite and verify build

- [ ] **Step 1: Run tests**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && pnpm test`
Expected: All tests pass

- [ ] **Step 2: Run TypeScript check**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Run lint**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && pnpm lint`
Expected: No errors

- [ ] **Step 4: Commit any fixes if needed**
