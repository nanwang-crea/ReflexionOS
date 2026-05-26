# Multi-File Tabs & View Mode Switching Design

## Problem

The code editor currently supports only a single open file. Every file is opened in a side-by-side diff view (original vs. modified), even when the user just wants to read or edit a file. There is no way to open multiple files, switch between them, or view a file without the diff chrome.

## Design

### 1. Multi-Tab State Model

Replace the single-file `activeFile` with an array of open files and an active ID.

**Before** (`codeTabStore.ts`):
```ts
activeFile: ActiveFile | null
isDirty: boolean
```

**After**:
```ts
openFiles: OpenFile[]
activeFileId: string | null

interface OpenFile {
  id: string
  path: string
  language: string
  isDirty: boolean
  viewMode: 'edit' | 'diff'
  modifiedContent?: string
  originalContent?: string
}
```

Store operations:
- `openFile(path, viewMode)` — add file to `openFiles` if not present, set as active
- `closeFile(id)` — remove from `openFiles`, activate adjacent tab
- `setViewMode(id, mode)` — switch view mode for a single tab
- `setDirty(id, isDirty, modifiedContent?)` — update dirty state
- `clearDirty(id)` — after save

### 2. Tab Bar

Replace the current `CodeTabBar` (single-file action bar) with a real tab bar:

```
┌──────────┬──────────┬──────────┬──────────────────────────┐
│ ● app.py │  main.ts │  test.py │                  [Edit⇄] │
└──────────┴──────────┴──────────┴──────────────────────────┘
```

- Each tab: filename + `●` dirty indicator + close button (×)
- Right side: **Edit / Diff toggle button** (global for active tab)
- No dedicated Save button — save via Cmd+S or the editor's built-in action
- Tabs scroll horizontally when they overflow

### 3. View Modes

**Edit view** (default from file tree):
- Monaco `Editor` (single pane)
- Content loaded via `fileApi.getContent()`
- Full-featured code editor with syntax highlighting

**Diff view** (default from git changes):
- Monaco `DiffEditor` (side-by-side, right pane editable)
- Content loaded via `fileApi.getDiffContent()`
- Same as current behavior

**View mode toggle**: The button in the tab bar toggles `viewMode` for the active tab. Switching from edit → diff reloads via `getDiffContent()`. Switching from diff → edit reloads via `getContent()`.

### 4. Smart View Selection

Entry points pass a `viewMode` hint:

| Entry point | viewMode |
|---|---|
| File tree click | `'edit'` |
| Git changes click | `'diff'` |
| Chat ActionReceipt (explore category) | `'edit'` |
| Chat ActionReceipt (edit/create/delete category) | `'diff'` |

When a file is already open, `openFile` activates the existing tab without changing its current `viewMode`. The user can toggle manually.

### 5. Dirty State Preservation

Switching between tabs preserves each file's dirty state and `modifiedContent`. The `●` indicator shows which tabs have unsaved changes. No confirmation dialog on tab switch — the user can return to any tab and continue editing or save.

### 6. Component Changes

| Component | Change |
|---|---|
| `codeTabStore.ts` | Multi-file state, `openFile`/`closeFile`/`setViewMode`/`setDirty` actions |
| `CodeTabBar.tsx` | Rebuild as multi-tab bar with dirty indicators, close buttons, and Edit/Diff toggle |
| `CodeTab.tsx` | Route to `CodeEditor` or `EditableDiffViewer` based on `viewMode`; manage per-file content state from store |
| New `CodeEditor.tsx` | Single-pane Monaco Editor for edit view |
| `EditableDiffViewer.tsx` | Keep as-is (diff view) |
| `FileTreeItem.tsx` | Call `openFile(path, 'edit')` |
| `GitFileItem.tsx` | Call `openFile(path, 'diff')` |
| `AgentWorkspace.tsx` | Pass `viewMode` hint in `handleDetailClick` |

### 7. Data Flow

```
User clicks file (tree/git/chat)
  ↓
codeTabStore.openFile(path, viewMode)
  → if file already open: activate tab, keep current viewMode
  → if new: add OpenFile to openFiles, set as active
  ↓
CodeTab detects activeFileId change
  → reads active OpenFile from store
  → if viewMode='edit': fetch via getContent(), render CodeEditor
  → if viewMode='diff': fetch via getDiffContent(), render EditableDiffViewer
  ↓
User edits → update openFile.isDirty + modifiedContent in store
User toggles view → setViewMode(id, newMode), re-fetch content
User saves → fileApi.writeFile(), clearDirty(id)
User closes tab → closeFile(id), activate neighbor
```

### 8. Edge Cases

- **Close the only open tab**: `activeFileId` becomes `null`, show empty state
- **Close a dirty tab**: Close immediately (no confirmation), dirty state is lost — matches user's choice of no confirmation dialogs
- **Reopen a previously closed file**: Opens fresh (no cached content from before)
- **View mode toggle while dirty**: Switches view; diff view shows current modified content vs. original
