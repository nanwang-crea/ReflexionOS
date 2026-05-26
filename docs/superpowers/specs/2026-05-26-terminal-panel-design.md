# Terminal Panel Design

## Overview

Add a resizable, hideable terminal panel at the bottom of the AgentWorkspace in code mode. The terminal is a full-featured shell powered by xterm.js + node-pty over Electron IPC, with multi-instance tab support.

## Layout

Terminal panel sits at the workspace level (below CodeTab), not inside CodeTab. This ensures the terminal persists across file switches and keeps concerns separated.

```
┌──────────┬─────────────────────────────────────┐
│ FileSide │  WorkspaceHeader                    │
│ bar      │─────────────────────────────────────│
│          │  CodeTab (flex-1, min-h-0)          │
│          │  ├─ CodeTabBar                      │
│          │  └─ EditableDiffViewer              │
│          │─────────────────────────────────────│
│          │  [drag bar] 4px                      │
│          │─────────────────────────────────────│
│          │  TerminalPanel (resizable height)    │
│          │  ├─ TerminalTabBar (终端1|终端2|+|✕) │
│          │  └─ xterm.js instance                │
└──────────┴─────────────────────────────────────┘
```

- Terminal panel only visible in code mode
- Draggable height: min 100px, max 60vh, default 200px
- Fully hideable (click ✕ or Ctrl+`), editor takes full space when hidden
- Restores previous height when re-shown

## Terminal Implementation

### Data Flow

```
xterm.js (renderer) ←→ preload.cjs ←→ ipcMain (main) ←→ node-pty (child process)
```

### Main Process (electron/main.cjs)

New IPC handlers:

| Handler | Purpose |
|---------|---------|
| `terminal:create` | Spawn PTY via `node-pty.spawn()`, cwd = current project path. Return `{ id, pid }`. |
| `terminal:write` | Write data to PTY stdin: `pty.write(data)` |
| `terminal:resize` | Resize PTY: `pty.resize(cols, rows)` |
| `terminal:kill` | Kill PTY process: `pty.kill()` |

PTY `onData` sends data back via `mainWindow.webContents.send('terminal:data', id, data)`.  
PTY `onExit` sends via `mainWindow.webContents.send('terminal:exit', id, exitCode)`.

### Preload (electron/preload.cjs)

Expose `terminal` API on `window.electronAPI`:

- `create(cwd: string): Promise<{id: string, pid: number}>`
- `write(id: string, data: string): void`
- `resize(id: string, cols: number, rows: number): void`
- `kill(id: string): void`
- `onData(callback: (id: string, data: string) => void): () => void` — returns unsubscribe
- `onExit(callback: (id: string, exitCode: number) => void): () => void` — returns unsubscribe

### Renderer Process

- `TerminalInstance` component uses `@xterm/xterm` + `@xterm/addon-fit`
- `onData` callback writes to xterm instance
- Keyboard input sent via `electronAPI.terminal.write(id, data)`
- `addon-fit` auto-adapts to container size, syncs resize to PTY

## State Management

New store: `frontend/src/features/terminal/terminalStore.ts` (Zustand)

```typescript
interface TerminalInstance {
  id: string
  title: string        // e.g. "终端 1"
  ptyPid: number | null
  exited: boolean
}

interface TerminalState {
  instances: TerminalInstance[]
  activeTerminalId: string | null
  panelVisible: boolean
  panelHeight: number     // default 200, min 100, max 60vh
}

interface TerminalActions {
  createTerminal: (cwd: string) => void
  closeTerminal: (id: string) => void
  setActiveTerminal: (id: string) => void
  togglePanel: () => void
  setPanelHeight: (height: number) => void
  markExited: (id: string) => void
}
```

- `panelVisible` persisted to localStorage via Zustand persist middleware
- Switching to code mode: if `panelVisible` is true, panel renders automatically
- Switching to chat mode: panel not rendered, but PTY processes stay alive

## Component Structure

```
TerminalPanel/
├── TerminalPanel.tsx        # Panel container + drag bar + height control
├── TerminalInstance.tsx     # Single xterm.js instance (lifecycle + data binding)
└── TerminalTabBar.tsx       # Tab bar: 终端1 | 终端2 | + | ✕
```

- `TerminalPanel` manages drag-to-resize and panel visibility
- `TerminalInstance` manages xterm create/destroy/data binding per terminal
- `TerminalTabBar` manages tab switching, new terminal creation, and panel close

## Error Handling

| Scenario | Behavior |
|----------|----------|
| PTY process exits | Main process notifies renderer; xterm shows exit message; tab marked as exited; user can click to recreate |
| Window close | `before-quit` kills all PTY processes (already in existing logic) |
| Project switch | Close all terminals; new terminals use new project path as cwd |
| Drag height | mousedown on drag bar registers mousemove/mouseup; clamp to 100px–60vh range |

## Visual Theme

Match existing dark editor style:
- Background: `#1a1a2e`
- Text: green (`#0f0`) for prompt output
- Tab bar: `#16213e` background
- Active tab: `#0f3460` background
- Consistent with Monaco editor dark theme already in use

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+\` | Toggle terminal panel visibility |
| Ctrl+Shift+\` | Create new terminal |

## Dependencies to Add

- `@xterm/xterm` — terminal emulator renderer
- `@xterm/addon-fit` — auto-resize addon
- `node-pty` — pseudo-terminal (Electron main process only)
