# File Sidebar + Editable Diff — Design

## Summary

Enhance the Code tab with a **global file sidebar** (collapsible, visible in both Chat and Code tabs) that shows a full project file tree with git status markers, and merge the Diff/Edit views into a single **editable DiffEditor** (right pane writable).

## Requirements

- Global collapsible sidebar between the navigation sidebar and main content, always visible
- File tree with folders (expand/collapse) and files, plus git status markers (M/A/D/U)
- Backend API returns full directory tree + git status
- Merge Diff and Edit into one view: Monaco DiffEditor with editable right pane
- Remove the Diff/Edit sub-tab switcher
- Click file in tree → open in Code tab's editable diff viewer
- Sidebar toggle (expand/collapse) persisted in store

## Layout

```
┌──────────┬──────────────┬──────────────────────────────┐
│          │  File Sidebar │  Main Content                │
│ Nav      │  (collapsible)│  (Chat tab or Code tab)      │
│ Sidebar  │  240px        │  flex-1                      │
│ 256px    │              │                              │
│          │  📁 src ▼    │                              │
│          │    📝 app.ts M│  Editable Diff or Chat       │
│          │    📝 util.ts │                              │
│          │  📝 pkg.json A│                              │
└──────────┴──────────────┴──────────────────────────────┘
```

- File sidebar sits between nav sidebar and main content
- Collapsible via toggle button; width 240px when open, 0 when closed
- Sidebar state (open/closed) persisted in `codeTabStore`

## File Sidebar

### File Tree Component

- Recursive tree rendering with expand/collapse for directories
- Expand/collapse state persisted in `codeTabStore`
- Excluded directories: `node_modules`, `.git`, `__pycache__`, `.venv`, `__pycache__`, `.ruff_cache`, `.pytest_cache`, `dist`, `build`

### Git Status Markers

Each file node has an optional `gitStatus` field displayed as a colored badge:

| Status | Label | Color |
|--------|-------|-------|
| `"M"` | M | Green (text-emerald-600) |
| `"A"` | A | Green (text-emerald-600) |
| `"D"` | D | Red (text-red-500) |
| `"U"` | U | Gray (text-slate-400) |
| `null` | (none) | — |

### File Click Behavior

- Click a file → `setActiveFile(path, language)` → auto-switch to Code tab → load editable diff
- Click in Chat tab → auto-switches to Code tab

### Refresh

- Refresh button at top of sidebar reloads the file tree
- No automatic refresh (avoids polling overhead)

## Editable Diff Viewer

### Merge Diff and Edit

- Remove `CodeSubTab` type and Diff/Edit tab switching
- Remove `CodeTabBar`'s sub-tab buttons
- Simplify `CodeTabBar` to filename + save button only
- Replace `DiffViewer` + `CodeEditor` with single `EditableDiffViewer`

### EditableDiffViewer

- Monaco `DiffEditor` with `readOnly: false` on modified (right) pane
- Left pane: read-only git HEAD version (original)
- Right pane: current file content (modified), editable
- Changes to right pane trigger `onChange`, mark dirty
- Save submits right pane content to backend write API
- Save button always visible (right pane is always editable)

### CodeTab Simplification

- Always shows editable diff (no sub-tab switching)
- Loads both original + modified on file open
- File loading uses existing `GET /api/files/diff-content` endpoint

## Backend API

### `GET /api/files/tree`

Query params: `project_id`

Response:
```json
{
  "tree": [
    {
      "name": "src",
      "type": "directory",
      "path": "src",
      "children": [
        { "name": "app.ts", "type": "file", "path": "src/app.ts", "gitStatus": "M" },
        { "name": "utils.ts", "type": "file", "path": "src/utils.ts", "gitStatus": null }
      ]
    },
    {
      "name": "package.json",
      "type": "file",
      "path": "package.json",
      "gitStatus": "A"
    }
  ]
}
```

Implementation:
- Recursively walk project directory, skipping excluded dirs
- Run `git status --porcelain` to get changed files
- Map `git status` short codes to `M/A/D/U`
- Sort: directories first, then files, alphabetically within each group

## TypeScript Types

### FileTreeNode

```typescript
export type GitStatusCode = 'M' | 'A' | 'D' | 'U'

export interface FileTreeNode {
  name: string
  type: 'file' | 'directory'
  path: string
  gitStatus: GitStatusCode | null
  children?: FileTreeNode[]
}
```

## Store Changes

### codeTabStore additions

```typescript
// New state
sidebarOpen: boolean
expandedDirs: Set<string>
fileTree: FileTreeNode[] | null

// New actions
setSidebarOpen(open: boolean) => void
toggleDir(path: string) => void
setFileTree(tree: FileTreeNode[]) => void
```

### Remove

- `codeSubTab` state and `setCodeSubTab` action (no more sub-tab switching)

## Component Changes

### New Components

- `FileSidebar.tsx` — sidebar container with refresh button + tree
- `FileTreeItem.tsx` — recursive tree node (file or directory)
- `EditableDiffViewer.tsx` — Monaco DiffEditor with editable right pane

### Modified Components

- `CodeTab.tsx` — remove sub-tab logic, use EditableDiffViewer only
- `CodeTabBar.tsx` — remove Diff/Edit buttons, keep filename + save
- `App.tsx` or `AgentWorkspace.tsx` — add FileSidebar between nav sidebar and main content

### Removed Components

- `DiffViewer.tsx` — replaced by EditableDiffViewer
- `CodeEditor.tsx` — replaced by EditableDiffViewer

## Dependencies

No new dependencies. Uses existing `@monaco-editor/react`, `lucide-react`, `zustand`.
