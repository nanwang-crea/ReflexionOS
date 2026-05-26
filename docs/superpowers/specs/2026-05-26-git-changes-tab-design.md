# Git Changes Tab + Git Workflow — Design

## Summary

Add a **tab switcher** to the FileSidebar with two tabs: "Files" (existing file tree) and "Changes" (git-changed files overview with full git workflow). The Changes tab provides a VSCode-like Source Control experience including branch status display, stage/unstage, commit, push/pull, stash, and discard operations — all within the FileSidebar.

## Requirements

- FileSidebar top: tab switcher with "Files" and "Changes" tabs
- "Files" tab: existing file tree (unchanged)
- "Changes" tab: list of all git-changed files grouped into Staged and Unstaged sections
- Branch status display: current branch name + ahead/behind counts
- Stage/unstage individual files
- Commit with message input
- Push/pull/stash operations
- Discard changes on individual files
- Click changed file → open diff view in Code tab
- Changes tab badge showing count of changed files
- Full backend API for git operations with security checks

## Layout

### FileSidebar with Tabs

```
┌─────────────────────────────┐
│ 🔄  [文件]  [变更 3]    ✕  │  ← Refresh + Tab bar + Close
├─────────────────────────────┤
│                             │
│  (Active tab content)       │
│                             │
└─────────────────────────────┘
```

- Tab bar: two equal-width buttons below the refresh/close row
- Active tab: `accent` color + bottom indicator line
- Inactive tab: `content-secondary` color
- "Changes" tab shows badge with number of total changed files when > 0
- Switching tabs does not affect file tree expand state
- Switching to "Changes" tab auto-fetches git status

### Changes Tab Layout

```
┌─────────────────────────────┐
│  分支: main  ↑2 ↓1          │  ← GitBranchBar
├─────────────────────────────┤
│ ▼ Staged Changes (2)        │  ← GitFileGroup (collapsible)
│   ✓ src/app.tsx    [M]  ⊟   │  ← GitFileItem
│   ✓ src/util.ts    [A]  ⊟   │
├─────────────────────────────┤
│ ▼ Changes (3)               │  ← GitFileGroup (collapsible)
│   ○ src/api.ts     [M]  ⊞   │
│   ○ src/types.ts   [M]  ⊞   │
│   ○ README.md      [D]  ⊞   │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │ commit message...       │ │  ← GitCommitInput
│ └─────────────────────────┘ │
│ [✓ Commit]                  │
├─────────────────────────────┤
│ [⬆ Push] [⬇ Pull] [☰ Stash]│  ← GitActionBar
└─────────────────────────────┘
```

## Git Status Codes

| Status | Label | Color | Meaning |
|--------|-------|-------|---------|
| M | M | Green (status-success) | Modified |
| A | A | Green (status-success) | Added |
| D | D | Red (status-error) | Deleted |
| U | U | Gray (content-muted) | Untracked |
| R | R | Blue (accent) | Renamed |

## Interaction Details

### File Click
- Click a changed file name → open diff view (switch to Code tab, load file with diff)

### Stage/Unstage
- Stage button (⊞) on unstaged file → POST `/api/git/stage` → refresh status
- Unstage button (⊟) on staged file → POST `/api/git/unstage` → refresh status
- File moves between Staged/Changes sections with animation

### Commit
- Text input for commit message (multi-line, min 1 row, max 4 rows)
- Commit button enabled only when staged files exist and message is non-empty
- Commit button uses `accent` color when enabled, `surface-tertiary` when disabled
- After successful commit → refresh git status + branch info, clear message

### Push/Pull
- Push button: POST `/api/git/push`, shows loading spinner during execution
- Pull button: POST `/api/git/pull`, shows loading spinner during execution
- Both refresh status + branch info on completion
- NETWORK_OUT operations — backend already classifies these; no additional approval in UI

### Stash
- Stash button: POST `/api/git/stash` with `{ action: 'push' | 'pop' }`
- Default action: 'push' (git stash)
- Dropdown/alternate click: 'pop' (git stash pop)
- Refreshes status on completion

### Discard Changes
- Available via right-click menu or hover icon on each file
- POST `/api/git/discard` with file paths
- Shows confirmation toast before executing
- WRITE_PROJECT level operation

### Collapsible Sections
- Staged Changes and Changes sections are independently collapsible
- Default state: both expanded
- Collapse state persisted in gitStore

### Branch Info Bar
- Shows current branch name (clickable — future: branch switcher)
- Shows ahead/behind counts as `↑N ↓M`
- If no remote tracking: just branch name
- Refreshed whenever git status is refreshed

## Backend API

### New Endpoint Group: `/api/git/`

All endpoints require `project_id` query parameter.

#### `GET /api/git/status`

Returns complete git status for a project.

Response:
```json
{
  "branch": "main",
  "ahead": 2,
  "behind": 1,
  "staged": [
    { "path": "src/app.tsx", "status": "M", "insertions": 12, "deletions": 3 },
    { "path": "src/util.ts", "status": "A", "insertions": 45, "deletions": 0 }
  ],
  "unstaged": [
    { "path": "src/api.ts", "status": "M", "insertions": 5, "deletions": 2 }
  ],
  "untracked": [
    { "path": "new-file.ts", "status": "U" }
  ]
}
```

Implementation:
- `git status --porcelain` → parse XY codes into staged/unstaged/untracked
- `git rev-parse --abbrev-ref HEAD` → branch name
- `git rev-list --left-right --count @{upstream}...HEAD` → ahead/behind (graceful fallback if no upstream)
- `git diff --cached --numstat` → staged insertions/deletions
- `git diff --numstat` → unstaged insertions/deletions

#### `POST /api/git/stage`

Body: `{ "project_id": "...", "paths": ["src/app.tsx"] }`

Implementation: `git add <paths>` with path security validation

#### `POST /api/git/unstage`

Body: `{ "project_id": "...", "paths": ["src/app.tsx"] }`

Implementation: `git reset HEAD -- <paths>`

#### `POST /api/git/commit`

Body: `{ "project_id": "...", "message": "fix: resolve issue" }`

Implementation: `git commit -m <message>`

#### `POST /api/git/push`

Body: `{ "project_id": "..." }`

Implementation: `git push`

#### `POST /api/git/pull`

Body: `{ "project_id": "..." }`

Implementation: `git pull`

#### `POST /api/git/stash`

Body: `{ "project_id": "...", "action": "push" | "pop" }`

Implementation: `git stash` or `git stash pop`

#### `POST /api/git/discard`

Body: `{ "project_id": "...", "paths": ["src/api.ts"] }`

Implementation: `git checkout -- <paths>` for tracked files, `rm <paths>` for untracked files

### Security

- Path validation: all file paths validated against path traversal using existing `path_security.py`
- Operation classification: push/pull are NETWORK_OUT, discard is WRITE_PROJECT — backend enforces existing security policy
- Commit/stage/unstage are safe project-local operations
- Project scope: all operations are scoped to the project root directory

### Error Handling

- Git command failures return structured error: `{ "error": "git operation failed", "detail": "...", "stderr": "..." }`
- Not a git repo → 400 with clear message
- Merge conflicts during pull → error with conflict file list
- Push rejected → error with remote message

## Frontend Architecture

### New Store: `features/git/gitStore.ts`

```typescript
interface GitFileChange {
  path: string
  status: 'M' | 'A' | 'D' | 'U' | 'R'
  insertions?: number
  deletions?: number
}

interface GitStore {
  // Data
  branchInfo: { name: string; ahead: number; behind: number } | null
  stagedFiles: GitFileChange[]
  unstagedFiles: GitFileChange[]
  untrackedFiles: GitFileChange[]

  // UI state
  sidebarTab: 'files' | 'changes'
  stagedCollapsed: boolean
  unstagedCollapsed: boolean
  commitMessage: string
  isLoading: boolean
  isCommitting: boolean
  isPushing: boolean
  isPulling: boolean

  // Computed
  totalChanges: number  // staged + unstaged + untracked length

  // Actions
  fetchStatus(): Promise<void>
  fetchBranchInfo(): Promise<void>
  refreshAll(): Promise<void>  // fetchStatus + fetchBranchInfo
  stageFiles(paths: string[]): Promise<void>
  unstageFiles(paths: string[]): Promise<void>
  commit(message: string): Promise<void>
  push(): Promise<void>
  pull(): Promise<void>
  stash(action: 'push' | 'pop'): Promise<void>
  discardChanges(paths: string[]): Promise<void>
  setSidebarTab(tab: 'files' | 'changes'): void
  setCommitMessage(msg: string): void
  toggleStagedCollapsed(): void
  toggleUnstagedCollapsed(): void
}
```

### New API Client: `features/git/gitApi.ts`

```typescript
export const gitApi = {
  getStatus(projectId: string): Promise<GitStatusResponse>
  stageFiles(projectId: string, paths: string[]): Promise<void>
  unstageFiles(projectId: string, paths: string[]): Promise<void>
  commit(projectId: string, message: string): Promise<void>
  push(projectId: string): Promise<void>
  pull(projectId: string): Promise<void>
  stash(projectId: string, action: 'push' | 'pop'): Promise<void>
  discardChanges(projectId: string, paths: string[]): Promise<void>
}
```

### New Components

| Component | Purpose |
|-----------|---------|
| `GitChangesTab.tsx` | Changes tab container — renders branch bar + file groups + commit input + action bar |
| `GitBranchBar.tsx` | Branch name + ahead/behind display |
| `GitFileGroup.tsx` | Collapsible section for staged/unstaged/untracked file groups |
| `GitFileItem.tsx` | Single file row: icon + name + status badge + stage/unstage button + more menu |
| `GitCommitInput.tsx` | Multi-line commit message input + commit button |
| `GitActionBar.tsx` | Push/pull/stash buttons row |

### Modified Components

| Component | Change |
|-----------|--------|
| `FileSidebar.tsx` | Add tab switcher, conditionally render file tree or GitChangesTab |
| `codeTabStore.ts` | Add `sidebarTab` field (or delegate to gitStore) |

### Unchanged Components

| Component | Note |
|-----------|------|
| `FileTreeItem.tsx` | Files tab continues using existing git status badges from tree API |
| `fileApi.ts` | Tree API still returns per-file git_status (lightweight, for badges) |

## TypeScript Types

### `types/git.ts` (new file)

```typescript
export type GitStatusCode = 'M' | 'A' | 'D' | 'U' | 'R'

export interface GitFileChange {
  path: string
  status: GitStatusCode
  insertions?: number
  deletions?: number
}

export interface GitBranchInfo {
  name: string
  ahead: number
  behind: number
}

export interface GitStatusResponse {
  branch: string
  ahead: number
  behind: number
  staged: GitFileChange[]
  unstaged: GitFileChange[]
  untracked: GitFileChange[]
}
```

## Data Flow

1. User switches to "Changes" tab → `gitStore.fetchStatus()` + `gitStore.fetchBranchInfo()`
2. Status response populates `stagedFiles`, `unstagedFiles`, `untrackedFiles`
3. User clicks stage → `gitStore.stageFiles([path])` → POST `/api/git/stage` → refresh status
4. User clicks unstage → `gitStore.unstageFiles([path])` → POST `/api/git/unstage` → refresh status
5. User types commit message → `gitStore.setCommitMessage(msg)`
6. User clicks commit → `gitStore.commit(msg)` → POST `/api/git/commit` → refresh status + branch info + clear message
7. User clicks push → `gitStore.push()` → POST `/api/git/push` → refresh branch info
8. User clicks file name → `codeTabStore.setActiveFile(path, '')` → switch to Code tab + load diff

## Dependencies

No new dependencies. Uses existing `lucide-react`, `zustand`, `tailwindcss`, `axios`.

## Testing

- Backend: pytest for git API routes (mock subprocess calls)
- Frontend: Vitest for gitStore actions (mock API calls)
- Manual: verify stage/unstage/commit cycle, branch display, discard confirmation
