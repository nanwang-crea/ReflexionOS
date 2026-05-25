# File Sidebar + Editable Diff — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global collapsible file sidebar with project file tree + git status markers, and merge the Diff/Edit views into a single editable DiffEditor.

**Architecture:** Backend adds a `/api/files/tree` endpoint returning directory tree + git status. Frontend adds FileSidebar + FileTreeItem components between nav sidebar and main content. DiffViewer + CodeEditor merge into EditableDiffViewer (Monaco DiffEditor with writable right pane). CodeTabBar simplified to filename + save only.

**Tech Stack:** FastAPI (backend), React + TypeScript + Zustand + TailwindCSS + Monaco Editor (frontend)

---

## File Structure

### New Files

| File | Responsibility |
|------|----------------|
| `backend/app/models/file_tree.py` | Pydantic models for file tree response |
| `frontend/src/types/fileTree.ts` | TypeScript types for FileTreeNode |
| `frontend/src/components/workspace/FileSidebar.tsx` | Sidebar container with refresh + tree |
| `frontend/src/components/workspace/FileTreeItem.tsx` | Recursive tree node component |
| `frontend/src/components/workspace/EditableDiffViewer.tsx` | Monaco DiffEditor with editable right pane |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/services/file_content_service.py` | Add `get_file_tree` method |
| `backend/app/models/file_content.py` | Add FileTreeResponse model (or use file_tree.py) |
| `backend/app/api/routes/files.py` | Add `GET /api/files/tree` route |
| `frontend/src/features/code/codeTabStore.ts` | Add sidebarOpen, expandedDirs, fileTree; remove codeSubTab |
| `frontend/src/features/code/fileApi.ts` | Add `getTree` API call |
| `frontend/src/components/workspace/CodeTab.tsx` | Use EditableDiffViewer, remove sub-tab logic |
| `frontend/src/components/workspace/CodeTabBar.tsx` | Remove Diff/Edit buttons, keep filename + save |
| `frontend/src/pages/AgentWorkspace.tsx` | Add FileSidebar, simplify handleDetailClick |
| `frontend/src/components/workspace/WorkspaceHeader.tsx` | Remove "对话/代码" tab from header (move to sidebar area) |

### Removed Files

| File | Reason |
|------|--------|
| `frontend/src/components/workspace/DiffViewer.tsx` | Replaced by EditableDiffViewer |
| `frontend/src/components/workspace/CodeEditor.tsx` | Replaced by EditableDiffViewer |

---

### Task 1: Backend — File Tree API

**Files:**
- Create: `backend/app/models/file_tree.py`
- Modify: `backend/app/services/file_content_service.py`
- Modify: `backend/app/api/routes/files.py`
- Test: `backend/tests/test_file_tree_api.py`

- [ ] **Step 1: Create Pydantic models**

Create `backend/app/models/file_tree.py`:

```python
from pydantic import BaseModel


class FileTreeNode(BaseModel):
    name: str
    type: str
    path: str
    git_status: str | None = None
    children: list["FileTreeNode"] | None = None


class FileTreeResponse(BaseModel):
    tree: list[FileTreeNode]
```

- [ ] **Step 2: Add get_file_tree method to FileContentService**

Add to `backend/app/services/file_content_service.py`:

```python
    EXCLUDED_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".mypy_cache",
        ".tox", ".eggs", "*.egg-info", ".idea", ".vscode",
    })

    async def get_file_tree(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)

        git_status_map = await self._get_git_status_map(project_path)

        tree = self._build_tree(project_path, project_path, git_status_map)
        return {"tree": tree}

    async def _get_git_status_map(self, project_path: str) -> dict[str, str]:
        try:
            result = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            if result.returncode != 0:
                return {}

            status_map: dict[str, str] = {}
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                if len(line) < 4:
                    continue
                code = line[:2].strip()
                filepath = line[3:].strip()
                if code in ("M", "R"):
                    status_map[filepath] = "M"
                elif code in ("A", "C"):
                    status_map[filepath] = "A"
                elif code == "D":
                    status_map[filepath] = "D"
                elif code in ("??", "!"):
                    status_map[filepath] = "U"
                else:
                    status_map[filepath] = code[0] if code else "M"
            return status_map
        except FileNotFoundError:
            return {}

    def _build_tree(self, root_path: str, current_path: str, git_status_map: dict[str, str]) -> list[dict]:
        try:
            entries = sorted(os.listdir(current_path))
        except PermissionError:
            return []

        dirs = []
        files = []

        for entry in entries:
            if entry.startswith(".") and entry not in (".env", ".env.local"):
                continue

            full_path = os.path.join(current_path, entry)
            rel_path = os.path.relpath(full_path, root_path)

            if os.path.isdir(full_path):
                if entry in self.EXCLUDED_DIRS:
                    continue
                dirs.append(entry)
            elif os.path.isfile(full_path):
                files.append(entry)

        result = []

        for d in dirs:
            full_path = os.path.join(current_path, d)
            rel_path = os.path.relpath(full_path, root_path)
            children = self._build_tree(root_path, full_path, git_status_map)
            result.append({
                "name": d,
                "type": "directory",
                "path": rel_path,
                "git_status": None,
                "children": children,
            })

        for f in files:
            full_path = os.path.join(current_path, f)
            rel_path = os.path.relpath(full_path, root_path)
            result.append({
                "name": f,
                "type": "file",
                "path": rel_path,
                "git_status": git_status_map.get(rel_path),
                "children": None,
            })

        return result
```

- [ ] **Step 3: Add API route**

Add to `backend/app/api/routes/files.py`:

Import:
```python
from app.models.file_tree import FileTreeResponse
```

Route:
```python
@router.get("/tree", response_model=FileTreeResponse)
async def get_file_tree(
    project_id: str = Query(..., description="项目 ID"),
):
    try:
        return await file_content_service.get_file_tree(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc
```

- [ ] **Step 4: Add test**

Add to `backend/tests/test_file_content_api.py`:

```python
    def test_get_file_tree(self, client, git_project):
        project_id = _create_project(client, git_project)

        resp = client.get("/api/files/tree", params={"project_id": project_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "tree" in data
        tree = data["tree"]
        names = [n["name"] for n in tree]
        assert "example.py" in names

        example_node = next(n for n in tree if n["name"] == "example.py")
        assert example_node["type"] == "file"
        assert example_node["path"] == "example.py"
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_file_content_api.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/file_tree.py backend/app/services/file_content_service.py backend/app/api/routes/files.py backend/tests/test_file_content_api.py
git commit -m "feat: add file tree API with git status markers"
```

---

### Task 2: Frontend — FileTreeNode Types + Update Store + API Client

**Files:**
- Create: `frontend/src/types/fileTree.ts`
- Modify: `frontend/src/features/code/codeTabStore.ts`
- Modify: `frontend/src/features/code/fileApi.ts`

- [ ] **Step 1: Create FileTreeNode types**

Create `frontend/src/types/fileTree.ts`:

```typescript
export type GitStatusCode = 'M' | 'A' | 'D' | 'U'

export interface FileTreeNode {
  name: string
  type: 'file' | 'directory'
  path: string
  git_status: GitStatusCode | null
  children?: FileTreeNode[] | null
}

export interface FileTreeResponse {
  tree: FileTreeNode[]
}
```

- [ ] **Step 2: Update codeTabStore — add sidebar state, remove codeSubTab**

Replace entire `frontend/src/features/code/codeTabStore.ts`:

```typescript
import { create } from 'zustand'

export type WorkspaceTab = 'chat' | 'code'

export interface ActiveFile {
  path: string
  language: string
}

interface CodeTabState {
  workspaceTab: WorkspaceTab
  activeFile: ActiveFile | null
  isDirty: boolean
  sidebarOpen: boolean
  expandedDirs: Record<string, boolean>
}

interface CodeTabActions {
  setWorkspaceTab: (tab: WorkspaceTab) => void
  setActiveFile: (path: string, language: string) => void
  setDirty: (dirty: boolean) => void
  clearActiveFile: () => void
  setSidebarOpen: (open: boolean) => void
  toggleDir: (path: string) => void
  setDirExpanded: (path: string, expanded: boolean) => void
}

export const useCodeTabStore = create<CodeTabState & CodeTabActions>()((set) => ({
  workspaceTab: 'chat',
  activeFile: null,
  isDirty: false,
  sidebarOpen: true,
  expandedDirs: {},

  setWorkspaceTab: (tab) => set({ workspaceTab: tab }),
  setActiveFile: (path, language) =>
    set({
      activeFile: { path, language },
      isDirty: false,
      workspaceTab: 'code',
    }),
  setDirty: (dirty) => set({ isDirty: dirty }),
  clearActiveFile: () => set({ activeFile: null, isDirty: false }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleDir: (path) =>
    set((state) => ({
      expandedDirs: { ...state.expandedDirs, [path]: !state.expandedDirs[path] },
    })),
  setDirExpanded: (path, expanded) =>
    set((state) => ({
      expandedDirs: { ...state.expandedDirs, [path]: expanded },
    })),
}))
```

- [ ] **Step 3: Add getTree to fileApi**

Add to `frontend/src/features/code/fileApi.ts`:

Import:
```typescript
import type { FileTreeResponse } from '@/types/fileTree'
```

Add method:
```typescript
  getTree: (projectId: string) =>
    apiClient.get<FileTreeResponse>('/api/files/tree', {
      params: { project_id: projectId },
    }),
```

- [ ] **Step 4: Fix AgentWorkspace — remove defaultSubTab from setActiveFile call**

In `frontend/src/pages/AgentWorkspace.tsx`, the `handleDetailClick` currently passes a third arg `defaultSubTab` to `setActiveFile`. Since we removed `codeSubTab`, simplify:

Change:
```typescript
  const handleDetailClick = useCallback((detail: ActionReceiptDetail) => {
    const path = detail.arguments?.path as string | undefined
    if (!path) return
    const defaultSubTab = detail.category === 'edit' || detail.category === 'create' ? 'diff' : 'edit'
    setActiveFile(path, '', defaultSubTab)
  }, [setActiveFile])
```
to:
```typescript
  const handleDetailClick = useCallback((detail: ActionReceiptDetail) => {
    const path = detail.arguments?.path as string | undefined
    if (!path) return
    setActiveFile(path, '')
  }, [setActiveFile])
```

- [ ] **Step 5: Fix WorkspaceHeader — remove CodeSubTab import**

In `frontend/src/components/workspace/WorkspaceHeader.tsx`, if there's an import of `CodeSubTab` from `codeTabStore`, remove it. The header only uses `WorkspaceTab` and `workspaceTab`/`setWorkspaceTab`.

- [ ] **Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/fileTree.ts frontend/src/features/code/codeTabStore.ts frontend/src/features/code/fileApi.ts frontend/src/pages/AgentWorkspace.tsx frontend/src/components/workspace/WorkspaceHeader.tsx
git commit -m "feat: add file tree types, update store, remove codeSubTab"
```

---

### Task 3: Frontend — EditableDiffViewer Component

**Files:**
- Create: `frontend/src/components/workspace/EditableDiffViewer.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useRef, useEffect, useCallback } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import type { editor } from 'monaco-editor'

interface EditableDiffViewerProps {
  original: string
  modified: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

export function EditableDiffViewer({ original, modified, language, onChange, onSave }: EditableDiffViewerProps) {
  const editorRef = useRef<editor.IStandaloneDiffEditor | null>(null)

  function handleMount(ed: editor.IStandaloneDiffEditor) {
    editorRef.current = ed

    const modifiedEditor = ed.getModifiedEditor()
    modifiedEditor.onDidChangeModelContent(() => {
      const value = modifiedEditor.getValue()
      onChange(value)
    })

    modifiedEditor.addCommand(
      2048 | 49,
      () => onSave(),
    )
  }

  useEffect(() => {
    if (editorRef.current) {
      const originalModel = editorRef.current.getOriginalEditor().getModel()
      const modifiedModel = editorRef.current.getModifiedEditor().getModel()
      if (originalModel) originalModel.setValue(original)
      if (modifiedModel) modifiedModel.setValue(modified)
    }
  }, [original, modified])

  return (
    <DiffEditor
      height="100%"
      language={language}
      original={original}
      modified={modified}
      onMount={handleMount}
      options={{
        readOnly: false,
        renderSideBySide: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
        enableSplitViewResizing: true,
      } as editor.IDiffEditorConstructionOptions}
    />
  )
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit src/components/workspace/EditableDiffViewer.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/EditableDiffViewer.tsx
git commit -m "feat: add EditableDiffViewer with writable right pane"
```

---

### Task 4: Frontend — Update CodeTab and CodeTabBar

**Files:**
- Modify: `frontend/src/components/workspace/CodeTab.tsx`
- Modify: `frontend/src/components/workspace/CodeTabBar.tsx`
- Delete: `frontend/src/components/workspace/DiffViewer.tsx`
- Delete: `frontend/src/components/workspace/CodeEditor.tsx`

- [ ] **Step 1: Simplify CodeTabBar**

Replace entire `frontend/src/components/workspace/CodeTabBar.tsx`:

```typescript
import { Save } from 'lucide-react'

interface CodeTabBarProps {
  filename: string | null
  isDirty: boolean
  onSave: () => void
}

export function CodeTabBar({
  filename,
  isDirty,
  onSave,
}: CodeTabBarProps) {
  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2">
      <div className="flex items-center gap-2">
        {filename && (
          <span className="text-sm text-slate-600">
            {isDirty && <span className="mr-1 text-amber-500">●</span>}
            {filename}
          </span>
        )}
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={!isDirty}
        className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Save className="h-3.5 w-3.5" />
        保存
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Update CodeTab to use EditableDiffViewer**

Replace entire `frontend/src/components/workspace/CodeTab.tsx`:

```typescript
import { useCallback, useEffect, useState } from 'react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { CodeTabBar } from './CodeTabBar'
import { EditableDiffViewer } from './EditableDiffViewer'
import { useProjectStore } from '@/stores/projectStore'

function CodeTabEmpty() {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      从左侧文件栏选择文件查看变更
    </div>
  )
}

function CodeTabLoading() {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      加载中...
    </div>
  )
}

export function CodeTab() {
  const activeFile = useCodeTabStore((s) => s.activeFile)
  const isDirty = useCodeTabStore((s) => s.isDirty)
  const setDirty = useCodeTabStore((s) => s.setDirty)

  const currentProject = useProjectStore((s) => s.currentProject)
  const projectId = currentProject?.id ?? ''

  const [original, setOriginal] = useState('')
  const [modified, setModified] = useState('')
  const [language, setLanguage] = useState('plaintext')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!activeFile || !projectId) return

    const filePath = activeFile.path
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        const resp = await fileApi.getDiffContent(projectId, filePath)
        if (cancelled) return
        const data = resp.data
        setOriginal(data.original)
        setModified(data.modified)
        setLanguage(data.language)
      } catch (err) {
        if (cancelled) return
        console.error('Failed to load file:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [activeFile, projectId])

  const handleChange = useCallback(
    (_value: string) => {
      setDirty(true)
    },
    [setDirty],
  )

  const handleSave = useCallback(async () => {
    if (!activeFile || !projectId) return
    try {
      const rightContent = modified
      const resp = await fileApi.writeFile({
        project_id: projectId,
        path: activeFile.path,
        content: rightContent,
      })
      if (resp.data.success) {
        setDirty(false)
      } else {
        console.error('Save failed:', resp.data.error)
      }
    } catch (err) {
      console.error('Save failed:', err)
    }
  }, [activeFile, projectId, modified, setDirty])

  if (!activeFile) {
    return <CodeTabEmpty />
  }

  const filename = activeFile.path.split('/').pop() ?? activeFile.path

  return (
    <div className="flex h-full flex-col">
      <CodeTabBar
        filename={filename}
        isDirty={isDirty}
        onSave={handleSave}
      />
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <CodeTabLoading />
        ) : (
          <EditableDiffViewer
            original={original}
            modified={modified}
            language={language}
            onChange={handleChange}
            onSave={handleSave}
          />
        )}
      </div>
    </div>
  )
}
```

Note: The `handleSave` reads `modified` state. Since EditableDiffViewer's `onChange` only sets dirty flag (not updating `modified` state directly), we need to also track the current modified content. We'll use a ref for the latest content:

Actually, the `onChange` in EditableDiffViewer fires with the new value but CodeTab's `handleChange` ignores the value. We need to update `modified` when the user edits. Let me fix:

Change `handleChange`:
```typescript
  const handleChange = useCallback(
    (value: string) => {
      setModified(value)
      setDirty(true)
    },
    [setDirty],
  )
```

And `handleSave` should use the current `modified` state which gets updated by handleChange. This works correctly.

- [ ] **Step 3: Delete old components**

```bash
rm frontend/src/components/workspace/DiffViewer.tsx frontend/src/components/workspace/CodeEditor.tsx
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workspace/CodeTab.tsx frontend/src/components/workspace/CodeTabBar.tsx
git rm frontend/src/components/workspace/DiffViewer.tsx frontend/src/components/workspace/CodeEditor.tsx
git commit -m "feat: merge Diff/Edit into EditableDiffViewer, simplify CodeTab"
```

---

### Task 5: Frontend — FileTreeItem Component

**Files:**
- Create: `frontend/src/components/workspace/FileTreeItem.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { ChevronDown, ChevronRight, File, Folder, FolderOpen } from 'lucide-react'
import type { FileTreeNode, GitStatusCode } from '@/types/fileTree'
import { useCodeTabStore } from '@/features/code/codeTabStore'

const GIT_STATUS_STYLES: Record<GitStatusCode, string> = {
  M: 'text-emerald-600',
  A: 'text-emerald-600',
  D: 'text-red-500',
  U: 'text-slate-400',
}

function GitStatusBadge({ status }: { status: GitStatusCode }) {
  return (
    <span className={`ml-auto text-xs font-mono ${GIT_STATUS_STYLES[status]}`}>
      {status}
    </span>
  )
}

export function FileTreeItem({ node, depth }: { node: FileTreeNode; depth: number }) {
  const expandedDirs = useCodeTabStore((s) => s.expandedDirs)
  const toggleDir = useCodeTabStore((s) => s.toggleDir)
  const setActiveFile = useCodeTabStore((s) => s.setActiveFile)
  const activeFile = useCodeTabStore((s) => s.activeFile)

  const isExpanded = expandedDirs[node.path] ?? false
  const isActive = activeFile?.path === node.path

  if (node.type === 'directory') {
    return (
      <div>
        <button
          type="button"
          onClick={() => toggleDir(node.path)}
          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm text-slate-700 hover:bg-slate-100"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          )}
          {isExpanded ? (
            <FolderOpen className="h-4 w-4 shrink-0 text-amber-500" />
          ) : (
            <Folder className="h-4 w-4 shrink-0 text-amber-500" />
          )}
          <span className="truncate">{node.name}</span>
        </button>
        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeItem key={child.path} node={child} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => setActiveFile(node.path, '')}
      className={`flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100 ${
        isActive ? 'bg-slate-100 text-slate-900 font-medium' : 'text-slate-600'
      }`}
      style={{ paddingLeft: `${depth * 12 + 8 + 20}px` }}
    >
      <File className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      <span className="truncate">{node.name}</span>
      {node.git_status && <GitStatusBadge status={node.git_status} />}
    </button>
  )
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit src/components/workspace/FileTreeItem.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/FileTreeItem.tsx
git commit -m "feat: add FileTreeItem component with git status badges"
```

---

### Task 6: Frontend — FileSidebar Component

**Files:**
- Create: `frontend/src/components/workspace/FileSidebar.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useEffect, useState } from 'react'
import { PanelLeftClose, PanelLeftOpen, RefreshCw } from 'lucide-react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { useProjectStore } from '@/stores/projectStore'
import { FileTreeItem } from './FileTreeItem'
import type { FileTreeNode } from '@/types/fileTree'

export function FileSidebar() {
  const sidebarOpen = useCodeTabStore((s) => s.sidebarOpen)
  const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)
  const currentProject = useProjectStore((s) => s.currentProject)

  const [tree, setTree] = useState<FileTreeNode[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!currentProject) return
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        const resp = await fileApi.getTree(currentProject.id)
        if (cancelled) return
        setTree(resp.data.tree)
      } catch (err) {
        if (cancelled) return
        console.error('Failed to load file tree:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [currentProject])

  if (!sidebarOpen) {
    return (
      <div className="flex flex-col items-center border-r border-gray-200 bg-white py-3">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          title="展开文件栏"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full w-60 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
        <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
          文件
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              if (!currentProject) return
              setLoading(true)
              fileApi.getTree(currentProject.id)
                .then((resp) => setTree(resp.data.tree))
                .catch((err) => console.error('Refresh failed:', err))
                .finally(() => setLoading(false))
            }}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            title="刷新"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            title="收起文件栏"
          >
            <PanelLeftClose className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {!currentProject ? (
          <div className="px-3 py-4 text-xs text-slate-400">请先选择项目</div>
        ) : loading ? (
          <div className="px-3 py-4 text-xs text-slate-400">加载中...</div>
        ) : (
          tree.map((node) => (
            <FileTreeItem key={node.path} node={node} depth={0} />
          ))
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit src/components/workspace/FileSidebar.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/FileSidebar.tsx
git commit -m "feat: add FileSidebar component with tree + refresh"
```

---

### Task 7: Frontend — Integrate FileSidebar into Layout

**Files:**
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **Step 1: Add FileSidebar to AgentWorkspace**

Add import:
```typescript
import { FileSidebar } from '@/components/workspace/FileSidebar'
```

In the JSX, add `FileSidebar` between the outer div and the main content. The current layout is:

```tsx
      <div className="flex h-full flex-col bg-white">
        <WorkspaceHeader ... />
        ...
      </div>
```

Wrap to include sidebar:
```tsx
      <div className="flex h-full">
        <FileSidebar />
        <div className="flex h-full flex-col bg-white flex-1 min-w-0">
          <WorkspaceHeader ... />
          ...
        </div>
      </div>
```

The outer `<div className="flex h-full flex-col bg-white">` becomes split: outer flex row with sidebar + inner flex col with header/content.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Run existing tests**

Run: `cd frontend && pnpm test`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: integrate FileSidebar into workspace layout"
```

---

### Task 8: Run All Tests + Lint

- [ ] **Step 1: Run backend tests**

Run: `cd backend && python -m pytest -v`
Expected: All tests pass

- [ ] **Step 2: Run frontend tests**

Run: `cd frontend && pnpm test`
Expected: All tests pass

- [ ] **Step 3: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Run linter**

Run: `cd frontend && pnpm lint`
Expected: No errors
