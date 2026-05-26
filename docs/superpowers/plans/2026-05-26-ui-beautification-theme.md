# UI Beautification & Theme System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement dual theme system (light/dark), three-column layout, terminal improvements, and component migration to semantic color tokens.

**Architecture:** CSS variables in `:root` / `.dark` selectors define theme tokens. Tailwind `darkMode: 'class'` maps custom color names to these variables. A `themeStore` persists user preference and syncs the `dark` class on `<html>`. Components migrate from hardcoded Tailwind colors to semantic token classes.

**Tech Stack:** React 18, Zustand, Tailwind CSS 3, CSS custom properties, xterm.js, lucide-react

---

## Task 1: Theme Store + CSS Variables + Tailwind Config

**Files:**
- Create: `src/stores/themeStore.ts`
- Modify: `src/index.css`
- Modify: `tailwind.config.js`
- Modify: `src/App.tsx`

- [ ] **Step 1: Create themeStore**

```typescript
// src/stores/themeStore.ts
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
}

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolveTheme(theme: ThemeMode): 'light' | 'dark' {
  return theme === 'system' ? getSystemTheme() : theme
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'light',
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: 'reflexion-theme',
      storage: createJSONStorage(() => localStorage),
    },
  ),
)

export function applyTheme(theme: ThemeMode) {
  const resolved = resolveTheme(theme)
  document.documentElement.classList.toggle('dark', resolved === 'dark')
}
```

- [ ] **Step 2: Add CSS variables to index.css**

Replace the current `:root` block in `src/index.css` with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  font-family: Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  font-weight: 400;

  --bg-primary: #ffffff;
  --bg-secondary: #f1f5f9;
  --bg-tertiary: #e2e8f0;
  --bg-code: #fafafa;
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #94a3b8;
  --border: #e2e8f0;
  --border-subtle: #f1f5f9;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --accent-soft: #dbeafe;

  --terminal-bg: #1e1e2e;
  --terminal-tabbar: #181825;
  --terminal-tab-active: #313244;

  --shadow-color: rgba(15, 23, 42, 0.12);

  color: var(--text-primary);
  background-color: var(--bg-primary);
}

.dark {
  --bg-primary: #1e1e2e;
  --bg-secondary: #181825;
  --bg-tertiary: #313244;
  --bg-code: #11111b;
  --text-primary: #cdd6f4;
  --text-secondary: #a6adc8;
  --text-muted: #6c7086;
  --border: #45475a;
  --border-subtle: #313244;
  --accent: #89b4fa;
  --accent-hover: #74c7ec;
  --accent-soft: #1e3a5f;

  --terminal-bg: #1e1e2e;
  --terminal-tabbar: #181825;
  --terminal-tab-active: #313244;

  --shadow-color: rgba(0, 0, 0, 0.4);
}

body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
}

#root {
  width: 100%;
  height: 100vh;
}
```

- [ ] **Step 3: Update tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        surface: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
          code: 'var(--bg-code)',
        },
        content: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        edge: {
          DEFAULT: 'var(--border)',
          subtle: 'var(--border-subtle)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          soft: 'var(--accent-soft)',
        },
        terminal: {
          bg: 'var(--terminal-bg)',
          tabbar: 'var(--terminal-tabbar)',
          'tab-active': 'var(--terminal-tab-active)',
        },
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 4: Wire up theme in App.tsx**

```typescript
// src/App.tsx
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
```

- [ ] **Step 5: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/themeStore.ts frontend/src/index.css frontend/tailwind.config.js frontend/src/App.tsx
git commit -m "feat: add theme system with CSS variables, themeStore, and Tailwind config"
```

---

## Task 2: Theme Toggle Button in Sidebar Footer

**Files:**
- Modify: `src/components/layout/WorkspaceSidebar.tsx`

- [ ] **Step 1: Add theme toggle to sidebar footer**

In `WorkspaceSidebar.tsx`, add imports:

```typescript
import { Moon, Sun, Monitor } from 'lucide-react'
import { useThemeStore } from '@/stores/themeStore'
```

Replace the footer section (currently `<div className="border-t border-slate-200 p-4">` with only Settings NavLink) with:

```tsx
<div className="border-t border-edge p-4">
  <div className="flex items-center justify-between">
    <NavLink
      to="/settings"
      className={({ isActive }) => `flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[15px] transition hover:bg-surface-tertiary ${
        isActive ? 'bg-surface-tertiary text-content-primary' : 'text-content-secondary'
      }`}
    >
      <Settings className="h-5 w-5" />
      <span className="font-medium">设置</span>
    </NavLink>
    <button
      type="button"
      onClick={() => {
        const current = useThemeStore.getState().theme
        const next = current === 'light' ? 'dark' : current === 'dark' ? 'system' : 'light'
        useThemeStore.getState().setTheme(next)
      }}
      className="rounded-lg p-1.5 text-content-muted transition hover:bg-surface-tertiary hover:text-content-secondary"
      title={`主题: ${useThemeStore.getState().theme}`}
    >
      {(() => {
        const theme = useThemeStore((s) => s.theme)
        if (theme === 'dark') return <Moon className="h-4 w-4" />
        if (theme === 'system') return <Monitor className="h-4 w-4" />
        return <Sun className="h-4 w-4" />
      })()}
    </button>
  </div>
</div>
```

- [ ] **Step 2: Migrate sidebar container to semantic tokens**

Change the sidebar `<aside>` className from:
`flex h-full w-64 shrink-0 flex-col border-r border-slate-200 bg-slate-100/80 lg:w-[320px]`

To:
`flex h-full w-64 shrink-0 flex-col border-r border-edge bg-surface-secondary lg:w-[320px]`

- [ ] **Step 3: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/WorkspaceSidebar.tsx
git commit -m "feat: add theme toggle button in sidebar footer"
```

---

## Task 3: Terminal Catppuccin Theme + CWD Fix

**Files:**
- Modify: `src/components/terminal/TerminalInstance.tsx`
- Modify: `src/components/terminal/TerminalTabBar.tsx`
- Modify: `src/components/terminal/TerminalPanel.tsx`

- [ ] **Step 1: Update TerminalInstance xterm theme**

In `TerminalInstance.tsx`, replace the entire `theme` object in `new Terminal({ theme: { ... } })` with:

```typescript
theme: {
  background: '#1e1e2e',
  foreground: '#cdd6f4',
  cursor: '#f5e0dc',
  cursorAccent: '#1e1e2e',
  selectionBackground: '#585b70',
  selectionForeground: '#cdd6f4',
  black: '#45475a',
  red: '#f38ba8',
  green: '#a6e3a1',
  yellow: '#f9e2af',
  blue: '#89b4fa',
  magenta: '#f5c2e7',
  cyan: '#94e2d5',
  white: '#bac2de',
  brightBlack: '#585b70',
  brightRed: '#f38ba8',
  brightGreen: '#a6e3a1',
  brightYellow: '#f9e2af',
  brightBlue: '#89b4fa',
  brightMagenta: '#f5c2e7',
  brightCyan: '#94e2d5',
  brightWhite: '#a6adc8',
},
```

- [ ] **Step 2: Fix TerminalTabBar CWD to use current project**

In `TerminalTabBar.tsx`, add import:

```typescript
import { useProjectStore } from '@/stores/projectStore'
```

Replace `handleNew`:

```typescript
const handleNew = () => {
  const cwd = useProjectStore.getState().currentProject?.path ?? ''
  createTerminal(cwd)
}
```

- [ ] **Step 3: Update TerminalPanel to use semantic tokens**

In `TerminalPanel.tsx`, change:
- Resize handle: `bg-blue-500` → `bg-accent`
- Tab bar area background: `bg-[#1a1a2e]` → `bg-terminal-bg`
- Container `overflow-hidden` stays

The terminal content area div:
`className="flex-1 overflow-hidden bg-[#1a1a2e] relative"`
→ `className="flex-1 overflow-hidden bg-terminal-bg relative"`

The panel container stays with `bg-terminal-bg` approach since terminal always uses dark.

- [ ] **Step 4: Update TerminalTabBar to use semantic tokens**

In `TerminalTabBar.tsx`, change:
- Background: `bg-[#16213e]` → `bg-terminal-tabbar`
- Active tab: `bg-[#0f3460]` → `bg-terminal-tab-active`
- Text colors remain as-is (white/slate on dark bg is fine for terminal)

- [ ] **Step 5: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/terminal/TerminalInstance.tsx frontend/src/components/terminal/TerminalTabBar.tsx frontend/src/components/terminal/TerminalPanel.tsx
git commit -m "feat: terminal Catppuccin theme, CWD follows current project, semantic tokens"
```

---

## Task 4: Three-Column Layout — Move FileSidebar to Right

**Files:**
- Modify: `src/pages/AgentWorkspace.tsx`
- Modify: `src/components/workspace/FileSidebar.tsx`
- Modify: `src/components/workspace/WorkspaceHeader.tsx`

- [ ] **Step 1: Move FileSidebar to right side in AgentWorkspace**

In `AgentWorkspace.tsx`, change the outer layout from:

```tsx
<div className="flex h-full">
  <FileSidebar />
  <div className="flex h-full flex-col bg-white flex-1 min-w-0">
    ...
  </div>
</div>
```

To:

```tsx
<div className="flex h-full">
  <div className="flex h-full flex-col bg-surface-primary flex-1 min-w-0">
    ...
  </div>
  {workspaceTab === 'code' && <FileSidebar />}
</div>
```

Remove the `import { FileSidebar } from './FileSidebar'` if it was removed from the left, and add the conditional render on the right.

Also change `bg-white` → `bg-surface-primary` in the main content div.

- [ ] **Step 2: Flip FileSidebar border and resize handle**

In `FileSidebar.tsx`, change:
- Container: `border-r border-gray-200 bg-white` → `border-l border-edge bg-surface-primary`
- Header border: `border-gray-100` → `border-edge-subtle`
- Close button icon: Change from `PanelLeftClose` to `PanelRightClose` (import from lucide-react)
- Resize handle: Move from `absolute left-0` to `absolute left-0` (stays on interior side, which is now the left edge of the right sidebar)

- [ ] **Step 3: Update WorkspaceHeader — remove sidebar toggle, keep terminal toggle**

In `WorkspaceHeader.tsx`:
- Remove the `FolderTree` sidebar toggle button (FileSidebar has its own close button)
- Keep the `TerminalSquare` toggle button
- Migrate colors: `border-gray-200 bg-white` → `border-edge bg-surface-primary`, `text-gray-900` → `text-content-primary`, `text-gray-500` → `text-content-muted`, `bg-slate-100` → `bg-surface-tertiary`, etc.
- Tab switcher: `bg-white` → `bg-surface-primary`, `text-slate-900` → `text-content-primary`

- [ ] **Step 4: Auto-toggle FileSidebar with workspace tab**

In `AgentWorkspace.tsx`, add an effect to auto-open/close FileSidebar when switching tabs:

```typescript
const workspaceTab = useCodeTabStore((s) => s.workspaceTab)
const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)

useEffect(() => {
  if (workspaceTab === 'code') {
    setSidebarOpen(true)
  } else {
    setSidebarOpen(false)
  }
}, [workspaceTab, setSidebarOpen])
```

- [ ] **Step 5: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AgentWorkspace.tsx frontend/src/components/workspace/FileSidebar.tsx frontend/src/components/workspace/WorkspaceHeader.tsx
git commit -m "feat: three-column layout with FileSidebar on right, auto-toggle with mode"
```

---

## Task 5: Migrate WorkspaceSidebar to Semantic Tokens

**Files:**
- Modify: `src/components/layout/WorkspaceSidebar.tsx`

- [ ] **Step 1: Migrate all hardcoded colors**

Systematic replacement in WorkspaceSidebar.tsx:

| From | To |
|------|----|
| `text-slate-700` | `text-content-secondary` |
| `text-slate-900` | `text-content-primary` |
| `text-slate-600` | `text-content-secondary` |
| `text-slate-500` | `text-content-muted` |
| `text-slate-400` | `text-content-muted` |
| `text-red-500` | `text-red-500` (keep, semantic) |
| `bg-slate-200/60` | `bg-surface-tertiary` |
| `bg-slate-200/70` | `bg-surface-tertiary` |
| `bg-slate-200` | `bg-surface-tertiary` |
| `hover:bg-slate-200` | `hover:bg-surface-tertiary` |
| `border-slate-200` | `border-edge` |
| `border-slate-300` | `border-edge` |
| `bg-white` | `bg-surface-primary` |
| `text-gray-900` | `text-content-primary` |
| `text-gray-500` | `text-content-muted` |
| `text-gray-600` | `text-content-secondary` |

For the `sidebarEntryClassName` constant:
`'flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[15px] text-content-secondary transition hover:bg-surface-tertiary'`

For the project modal overlay:
- `bg-black/30` stays
- Modal: `bg-white` → `bg-surface-primary`, `text-slate-900` → `text-content-primary`
- Input fields: `bg-white border-slate-200 text-slate-700` → `bg-surface-primary border-edge text-content-secondary`
- Create button: `bg-slate-900 text-white hover:bg-slate-800` → `bg-accent text-white hover:bg-accent-hover`

- [ ] **Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/WorkspaceSidebar.tsx
git commit -m "feat: migrate WorkspaceSidebar to semantic theme tokens"
```

---

## Task 6: Migrate Chat and Transcript Components

**Files:**
- Modify: `src/components/workspace/WorkspaceTranscript.tsx`
- Modify: `src/components/chat/ChatInput.tsx`
- Modify: `src/components/workspace/PlanProgress.tsx`

- [ ] **Step 1: Migrate WorkspaceTranscript**

Key replacements:
- `bg-white` → `bg-surface-primary`
- `text-slate-700` → `text-content-secondary`
- `text-slate-900` → `text-content-primary`
- `bg-slate-100` (user message bubble) → `bg-surface-tertiary`
- `border-amber-200 bg-amber-50 text-amber-900` (system notices) → keep amber (semantic color for warnings)
- `border-red-200 bg-red-50 text-red-800` → keep red (semantic color for errors)

- [ ] **Step 2: Migrate ChatInput**

Key replacements:
- `bg-white border-gray-200` → `bg-surface-primary border-edge`
- `text-slate-700` → `text-content-secondary`
- `border-gray-100` → `border-edge-subtle`
- `bg-blue-600` (send button) → `bg-accent hover:bg-accent-hover`
- `shadow-blue-500/30` → keep or use theme shadow
- `text-gray-600` → `text-content-secondary`
- `hover:bg-gray-100` → `hover:bg-surface-tertiary`

- [ ] **Step 3: Migrate PlanProgress**

Key replacements:
- `bg-white/95 backdrop-blur` → `bg-surface-primary/95 backdrop-blur`
- `border-slate-200` → `border-edge`
- `text-slate-900` → `text-content-primary`
- `text-slate-600` → `text-content-secondary`
- `bg-slate-50/80` → `bg-surface-secondary/80`

- [ ] **Step 4: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workspace/WorkspaceTranscript.tsx frontend/src/components/chat/ChatInput.tsx frontend/src/components/workspace/PlanProgress.tsx
git commit -m "feat: migrate chat/transcript components to semantic theme tokens"
```

---

## Task 7: Migrate Code Editor and Remaining Components

**Files:**
- Modify: `src/components/workspace/CodeTab.tsx`
- Modify: `src/components/workspace/CodeTabBar.tsx`
- Modify: `src/components/workspace/EditableDiffViewer.tsx`
- Modify: `src/components/workspace/FileTreeItem.tsx`
- Modify: `src/pages/SettingsPage.tsx`
- Modify: `src/pages/SkillsPage.tsx`
- Modify: `src/pages/PluginsPage.tsx`
- Modify: `src/pages/AutomationPage.tsx`

- [ ] **Step 1: Migrate CodeTab, CodeTabBar**

CodeTabBar:
- `border-b border-gray-200 bg-white px-4 py-2` → `border-b border-edge bg-surface-primary px-4 py-2`
- `text-slate-600` → `text-content-secondary`
- `border-slate-200 bg-white` (save button) → `border-edge bg-surface-primary`

- [ ] **Step 2: Migrate EditableDiffViewer — Monaco theme sync**

Add a computed Monaco theme that syncs with the app theme. In `EditableDiffViewer.tsx`:

```typescript
import { useThemeStore } from '@/stores/themeStore'

function getMonacoTheme(): string {
  const theme = useThemeStore.getState().theme
  const resolved = theme === 'system'
    ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme
  return resolved === 'dark' ? 'vs-dark' : 'vs'
}
```

Use the theme in the DiffEditor component. Add a subscription to theme changes.

- [ ] **Step 3: Migrate FileTreeItem**

Key replacements:
- `text-slate-700 hover:bg-slate-100` → `text-content-secondary hover:bg-surface-tertiary`
- `bg-slate-100 text-slate-900` (active) → `bg-surface-tertiary text-content-primary`
- `text-slate-400` → `text-content-muted`
- `text-amber-500` (folder icon) → `text-amber-500` (keep, semantic)

- [ ] **Step 4: Migrate remaining pages**

For each page (Settings, Skills, Plugins, Automation):
- `bg-white` → `bg-surface-primary`
- `text-slate-900` → `text-content-primary`
- `text-slate-600` → `text-content-secondary`
- `text-slate-500` → `text-content-muted`
- `border-slate-200` / `border-gray-200` → `border-edge`

- [ ] **Step 5: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `cd frontend && npx vitest run`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/workspace/CodeTab.tsx frontend/src/components/workspace/CodeTabBar.tsx frontend/src/components/workspace/EditableDiffViewer.tsx frontend/src/components/workspace/FileTreeItem.tsx frontend/src/pages/
git commit -m "feat: migrate code editor and remaining pages to semantic theme tokens"
```

---

## Task 8: Final Polish and Verification

**Files:**
- Modify: any files needing final fixes

- [ ] **Step 1: Visual verification in dev mode**

Run: `cd frontend && pnpm run dev`
Manually verify:
- Light theme looks correct (all components render with light colors)
- Dark theme toggle works (click moon icon in sidebar footer)
- System theme follows OS preference
- Terminal shows Catppuccin Mocha colors
- New terminal CWD follows current project
- Three-column layout: FileSidebar on right in code mode, hidden in chat mode
- No hardcoded white/slate colors remaining

- [ ] **Step 2: Build verification**

Run: `cd frontend && pnpm run build`
Expected: Build succeeds

- [ ] **Step 3: Run lint**

Run: `cd frontend && pnpm run lint`
Expected: No new errors

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: UI beautification complete — dual theme, three-column layout, terminal improvements"
```
