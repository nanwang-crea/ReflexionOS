# Code Tab with Monaco Editor — Design

## Summary

Add a **Code tab** to the Workspace view that lets users view diffs and edit files directly, triggered by clicking patch/file receipts in the chat. The Code tab and Chat tab are full-screen views switched via a top tab bar.

## Requirements

- Click a patch/file receipt in chat → auto-switch to Code tab showing that file
- Code tab has two sub-modes: **Diff** (read-only, original vs modified) and **Edit** (editable)
- Diff data sourced from git via backend API (not client-side patch computation)
- Edit mode allows direct file editing with save via backend API
- All file access goes through FastAPI backend (consistent with existing tool architecture)

## Layout

### Top Tab Bar

New tab bar above the transcript area with two tabs:

- **Chat** (default): existing `WorkspaceTranscript` + input box, unchanged
- **Code**: Monaco Editor workspace

Tab bar is a separate row positioned below `WorkspaceHeader` and above the content area.

### Code Tab Internal Layout

```
┌──────────────────────────────────────┐
│ [Diff] [Edit]    filename.ts   [保存] │  ← sub-tab bar + filename + save
├──────────────────────────────────────┤
│                                      │
│           Monaco Editor              │
│  Diff mode: side-by-side original/  │
│  modified   Edit mode: single editor │
│                                      │
└──────────────────────────────────────┘
```

- **Sub-tab bar**: `Diff` / `Edit` toggle, current filename display, save button (visible in Edit mode only)
- **Empty state** (no file open): "点击聊天中的文件操作查看变更，或在此浏览文件"

## Diff View

### Data Source

Backend API returns original + modified content:

- `original` = `git show HEAD:<path>` output (empty string if file not in HEAD)
- `modified` = current file content from disk

No client-side patch computation. The backend handles all git interactions.

### Rendering

- Monaco `DiffEditor` in side-by-side mode
- Both panes read-only in Diff mode
- Language mode auto-detected from file extension

### Edge Cases

| Scenario | original | modified |
|----------|----------|----------|
| New file (untracked) | empty string | current disk content |
| Deleted file | `git show HEAD:<path>` | empty string |
| Modified file | `git show HEAD:<path>` | current disk content |
| File not found | empty string | empty string |

## Edit View

### Editor

- Monaco Editor in standard single-pane mode
- Full editing capabilities: syntax highlighting, line numbers, search/replace, multi-cursor
- Language mode auto-detected from file extension

### Save

- Save button in sub-tab bar, or Ctrl+S / Cmd+S
- Calls backend write API
- Dirty indicator (dot in tab) when content differs from last saved state
- If file was modified externally (by agent) during editing, show conflict dialog: "文件已被外部修改，是否覆盖？"

### File Switching

- When user clicks a different receipt or opens another file:
  - If current file has unsaved changes → confirmation dialog
  - After confirm → load new file

## Receipt Click Interaction

### Clickable Receipts

`ActionReceiptDetailRow` entries with `category` of `edit`, `create`, or `delete` become clickable links.

### Click Flow

1. User clicks receipt row (e.g., "编辑 src/foo.ts")
2. Extract file path from `detail.arguments.path`
3. Determine default sub-tab:
   - Receipt is `patch` type with `patch` text → open Diff sub-tab
   - Receipt is `file` write → open Edit sub-tab
4. Auto-switch to Code tab, load file into Monaco

### Visual Feedback

- Clickable receipt rows: `cursor-pointer` + subtle background highlight on hover
- Click transition: brief animation when switching to Code tab

## Backend API

Three new endpoints, all under the existing FastAPI backend:

### `GET /api/files/content`

Query params: `project_id`, `path`

Response:
```json
{
  "content": "string",
  "language": "typescript",
  "exists": true
}
```

Reuses `FileTool` path security validation. `language` inferred from file extension.

### `GET /api/files/diff-content`

Query params: `project_id`, `path`

Response:
```json
{
  "original": "string (git HEAD version or empty)",
  "modified": "string (current disk content or empty)",
  "language": "typescript"
}
```

- `original`: obtained via `git show HEAD:<path>` in the project directory
- If file not tracked in git, `original` is empty string
- Reuses `PathSecurity` validation

### `POST /api/files/write`

Request body:
```json
{
  "project_id": "string",
  "path": "string",
  "content": "string"
}
```

Response:
```json
{
  "success": true,
  "error": null
}
```

Reuses `FileTool` write logic and `PathSecurity` validation.

## Frontend Component Architecture

### New Components

```
src/components/workspace/
  CodeTab.tsx          ← Container for Code tab, manages Diff/Edit sub-tab switching
  DiffViewer.tsx       ← Monaco DiffEditor wrapper (read-only)
  CodeEditor.tsx       ← Monaco Editor wrapper (editable)
  CodeTabBar.tsx       ← Sub-tab bar: [Diff] [Edit] + filename + save button
```

### New Store

```
src/stores/codeTabStore.ts  ← Zustand store
  State:
    - activeFile: { path: string, language: string } | null
    - subTab: 'diff' | 'edit'
    - isDirty: boolean
  Actions:
    - setActiveFile(path, language, defaultSubTab)
    - setSubTab(subTab)
    - setDirty(isDirty)
    - clearActiveFile()
```

### New Service

```
src/services/fileApi.ts
  - fetchFileContent(projectId, path) → { content, language, exists }
  - fetchDiffContent(projectId, path) → { original, modified, language }
  - writeToFile(projectId, path, content) → { success, error? }
```

### Modifications to Existing Components

- `WorkspaceTranscript` area: add Chat/Code tab bar above transcript
- `ActionReceiptDetailRow`: add click handler for `edit`/`create`/`delete` categories
- Parent workspace component: integrate `codeTabStore` and tab switching logic

## Dependencies

- `@monaco-editor/react` — React wrapper for Monaco Editor (~2MB bundle)
- No new backend Python dependencies needed — `subprocess` for git is already available

## Out of Scope

- Multi-file diff view / file tree browser
- Committing changes via git from the Code tab
- Submitting edits back to the agent as new patches
- Inline diff annotations in the chat transcript
