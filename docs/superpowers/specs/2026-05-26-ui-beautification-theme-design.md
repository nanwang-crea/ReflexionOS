# UI Beautification & Theme System Design

Date: 2026-05-26

## Overview

ReflexionOS 的 UI 需要全面美化，核心问题：

1. **视觉割裂** — 左侧 WorkspaceSidebar（浅色）与终端/编辑器（深色）风格不统一
2. **布局拥挤** — WorkspaceSidebar + FileSidebar 并列，空间浪费
3. **终端配色突兀** — 绿字深蓝背景（赛博朋克风）与整体不协调
4. **终端 CWD 错误** — 新建终端不跟随当前项目路径
5. **无主题切换** — 只有浅色主题，深色体验缺失

## Design Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 主题系统 | CSS 变量 + Tailwind `darkMode: 'class'` | 轻量、可扩展、与 Tailwind 生态兼容 |
| 深色配色 | Catppuccin Mocha | 柔和护眼、社区验证、适合 IDE 类应用 |
| 布局模式 | 三栏：左会话 + 中内容 + 右文件树(代码模式) | 参考 Xcode，空间利用最优 |
| 终端配色 | Catppuccin Mocha ANSI 16 色 | 与深色主题统一，VS Code 风格 |
| 终端 CWD | 跟随当前项目 path | 符合用户预期 |

---

## Section 1: Theme System

### Architecture

```
themeStore (Zustand + persist)
  theme: 'light' | 'dark' | 'system'
  resolvedTheme: 'light' | 'dark'  (computed)

index.css
  :root { --color-*: <light values> }
  .dark { --color-*: <dark values> }

tailwind.config.js
  darkMode: 'class'
  theme.extend.colors: mapped from CSS variables

App.tsx / useThemeEffect
  syncs <html class="dark"> with resolvedTheme
  listens to matchMedia for system mode
```

### themeStore

```typescript
interface ThemeStore {
  theme: 'light' | 'dark' | 'system'
  setTheme: (theme: 'light' | 'dark' | 'system') => void
}
```

Persisted to localStorage key `reflexion-theme`.

### CSS Variable Tokens

Define in `:root` and `.dark` selectors in `index.css`:

**Light theme (current base):**

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | #ffffff | Main backgrounds |
| `--bg-secondary` | #f1f5f9 (slate-100) | Sidebar, card backgrounds |
| `--bg-tertiary` | #e2e8f0 (slate-200) | Hover states, dividers |
| `--text-primary` | #0f172a (slate-900) | Headings, primary text |
| `--text-secondary` | #475569 (slate-600) | Body text |
| `--text-muted` | #94a3b8 (slate-400) | Placeholder, disabled |
| `--border` | #e2e8f0 (slate-200) | Borders |
| `--border-subtle` | #f1f5f9 (slate-100) | Light borders |
| `--accent` | #3b82f6 (blue-500) | Accent/primary actions |
| `--accent-hover` | #2563eb (blue-600) | Accent hover |

**Dark theme (Catppuccin Mocha):**

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | #1e1e2e | Base |
| `--bg-secondary` | #181825 | Mantle (sidebar, cards) |
| `--bg-tertiary` | #313244 | Surface0 (hover, elevated) |
| `--text-primary` | #cdd6f4 | Text |
| `--text-secondary` | #a6adc8 | Subtext1 |
| `--text-muted` | #6c7086 | Overlay0 |
| `--border` | #45475a | Surface1 |
| `--border-subtle` | #313244 | Surface0 |
| `--accent` | #89b4fa | Blue |
| `--accent-hover` | #74c7ec | Sapphire |

### Tailwind Integration

```javascript
// tailwind.config.js
module.exports = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        surface: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
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
        },
      },
    },
  },
}
```

Migration strategy: Replace hardcoded Tailwind colors (`bg-white`, `text-slate-900`, etc.) with semantic tokens (`bg-surface-primary`, `text-content-primary`, etc.) in each component.

### Theme Toggle UI

Add a theme toggle button in:
- WorkspaceSidebar footer (next to Settings link)
- Icon: Sun/Moon (lucide-react), cycles light → dark → system

---

## Section 2: Three-Column Layout

### Layout Structure

```
+---WorkspaceSidebar---+---Main Content Area---+---FileSidebar---+
|                      |                       |                 |
| Session list         | WorkspaceHeader       | File tree       |
| (always visible,     |                       | (code mode only |
|  collapsible)        | Chat OR Code+Terminal |  collapsible)   |
|                      |                       |                 |
+----------------------+-----------------------+-----------------+
```

### Changes to AgentWorkspace.tsx

Current structure:
```tsx
<div className="flex h-full">
  <FileSidebar />
  <div className="flex h-full flex-col bg-white flex-1 min-w-0">
    ...
  </div>
</div>
```

New structure:
```tsx
<div className="flex h-full">
  <div className="flex h-full flex-1 min-w-0">
    ... (WorkspaceHeader, content, terminal)
  </div>
  {workspaceTab === 'code' && <FileSidebar />}
</div>
```

WorkspaceSidebar remains in App.tsx (unchanged position). FileSidebar moves from inside AgentWorkspace to the right side, and only renders in code mode.

### FileSidebar Adjustments

- Border changes from `border-r` to `border-l`
- Resize handle moves from left edge to left edge (stays on the interior side)
- Auto-hide when switching to chat mode
- Auto-show when switching to code mode (respecting user's last sidebar width)

### Header Simplification

WorkspaceHeader currently has a sidebar toggle button for FileSidebar. Since FileSidebar is now on the right:
- Remove the sidebar toggle from header (FileSidebar has its own close button)
- Keep the terminal toggle button
- Tab switcher (对话/代码) remains in center

---

## Section 3: Terminal Improvements

### 3.1 Terminal Color Theme

Replace current cyberpunk theme with Catppuccin Mocha:

| ANSI Role | Current | New (Catppuccin) |
|-----------|---------|-------------------|
| background | #1a1a2e | #1e1e2e |
| foreground | #0f0 | #cdd6f4 |
| cursor | #0f0 | #f5e0dc |
| cursorAccent | - | #1e1e2e |
| selectionBackground | #0f3460 | #585b7040 |
| black | #1a1a2e | #45475a |
| red | #e74c3c | #f38ba8 |
| green | #0f0 | #a6e3a1 |
| yellow | #f1c40f | #f9e2af |
| blue | #3498db | #89b4fa |
| magenta | #9b59b6 | #f5c2e7 |
| cyan | #1abc9c | #94e2d5 |
| white | #ecf0f1 | #bac2de |
| brightBlack | #7f8c8d | #585b70 |
| brightRed | #e74c3c | #f38ba8 |
| brightGreen | #2ecc71 | #a6e3a1 |
| brightYellow | #f1c40f | #f9e2af |
| brightBlue | #3498db | #89b4fa |
| brightMagenta | #9b59b6 | #f5c2e7 |
| brightCyan | #1abc9c | #94e2d5 |
| brightWhite | #ecf0f1 | #a6adc8 |

Terminal content area background in TerminalPanel: `bg-[#1e1e2e]`
Tab bar background: `bg-[#181825]`
Active tab: `bg-[#313244]`

### 3.2 Terminal CWD — Follow Current Project

**TerminalTabBar.handleNew():**

Current:
```typescript
const cwd = instances.length > 0 ? instances[0].cwd : ''
```

New:
```typescript
const cwd = useProjectStore.getState().currentProject?.path ?? ''
```

Import `useProjectStore` in TerminalTabBar.

This ensures:
- New terminal opens in the current project directory
- Falls back to empty string → main.cjs uses `os.homedir()` → user home directory

### 3.3 Terminal Panel Styling

- Resize handle: use `bg-accent` instead of `bg-blue-500`
- Tab bar: use theme variables (`bg-surface-secondary`, `text-content-secondary`)
- Active tab: `bg-surface-tertiary text-content-primary`
- Panel container border-top: `border-t edge-subtle` when visible

---

## Section 4: Component Migration Checklist

Each component needs to migrate from hardcoded Tailwind colors to semantic tokens:

| Component | Key Changes |
|-----------|-------------|
| `App.tsx` | `bg-white` → `bg-surface-primary` |
| `WorkspaceSidebar` | `bg-slate-100/80` → `bg-surface-secondary`, text colors → content tokens |
| `WorkspaceHeader` | `bg-white border-gray-200` → `bg-surface-primary border-edge` |
| `WorkspaceTranscript` | `bg-white` → `bg-surface-primary` |
| `ChatInput` | `bg-white border-gray-200` → `bg-surface-primary border-edge` |
| `CodeTab` / `CodeTabBar` | borders → `border-edge` |
| `FileSidebar` | `bg-white border-r` → `bg-surface-primary border-l border-edge` |
| `FileTreeItem` | hover/active → `bg-surface-tertiary`, text → content tokens |
| `TerminalPanel` | backgrounds → theme variables |
| `TerminalTabBar` | backgrounds → theme variables |
| `EditableDiffViewer` | Monaco theme → sync with app theme |

### Monaco Editor Theme Sync

Create two Monaco theme objects:
- `reflexion-light`: based on `vs` with token colors matching light theme
- `reflexion-dark`: based on `vs-dark` with Catppuccin token colors

Switch Monaco theme when app theme changes.

---

## Section 5: Out of Scope

The following are noted but not part of this design:

- **Windows packaging**: node-pty native module packaging for Windows needs `electron-builder` config. Current code already has `cmd.exe` shell support. To be addressed in a separate task.
- **Terminal split panes**: Splitting terminal horizontally/vertically
- **Terminal profiles**: Custom shell configurations (bash, fish, etc.)
- **Sidebar drag-reorder**: Reordering sessions/projects

---

## Implementation Priority

1. **Theme system** (CSS variables, themeStore, Tailwind config, toggle) — foundation
2. **Terminal improvements** (colors, CWD fix) — quick wins
3. **Layout change** (three-column, FileSidebar right) — structural
4. **Component migration** (all components to semantic tokens) — systematic
5. **Monaco theme sync** — polish
