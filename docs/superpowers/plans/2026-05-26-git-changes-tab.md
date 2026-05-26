# Git Changes Tab + Git Workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-tab FileSidebar with "Files" (existing tree) and "Changes" (git workflow) tabs, plus full backend git API.

**Architecture:** Backend adds a new `/api/git/` route group with a `GitService` that wraps `git` subprocess calls. Frontend adds a `gitStore` (Zustand), `gitApi` client, `types/git.ts`, and 6 new components inside `components/workspace/git/`. The existing `FileSidebar` is modified to add a tab switcher and conditionally render the Files tree or Changes tab.

**Tech Stack:** FastAPI + asyncio.subprocess (backend), React + Zustand + Tailwind + lucide-react (frontend)

---

## File Structure

### Backend — New Files
- `backend/app/api/routes/git.py` — Git API route handlers
- `backend/app/services/git_service.py` — Git subprocess wrapper service
- `backend/app/models/git.py` — Pydantic request/response models

### Backend — Modified Files
- `backend/app/main.py` — Register git router

### Frontend — New Files
- `frontend/src/types/git.ts` — TypeScript types for git API
- `frontend/src/features/git/gitApi.ts` — API client for git endpoints
- `frontend/src/features/git/gitStore.ts` — Zustand store for git state
- `frontend/src/components/workspace/git/GitChangesTab.tsx` — Changes tab container
- `frontend/src/components/workspace/git/GitBranchBar.tsx` — Branch name + ahead/behind
- `frontend/src/components/workspace/git/GitFileGroup.tsx` — Collapsible file group
- `frontend/src/components/workspace/git/GitFileItem.tsx` — Single file row
- `frontend/src/components/workspace/git/GitCommitInput.tsx` — Commit input + button
- `frontend/src/components/workspace/git/GitActionBar.tsx` — Push/pull/stash buttons

### Frontend — Modified Files
- `frontend/src/components/workspace/FileSidebar.tsx` — Add tab switcher, render GitChangesTab
- `frontend/src/features/code/codeTabStore.ts` — Add `sidebarTab` field

---

## Task 1: Backend Git Models

**Files:**
- Create: `backend/app/models/git.py`

- [ ] **Step 1: Create git models file**

```python
from pydantic import BaseModel


class GitFileChange(BaseModel):
    path: str
    status: str
    insertions: int | None = None
    deletions: int | None = None


class GitStatusResponse(BaseModel):
    branch: str
    ahead: int
    behind: int
    staged: list[GitFileChange]
    unstaged: list[GitFileChange]
    untracked: list[GitFileChange]


class GitStageRequest(BaseModel):
    project_id: str
    paths: list[str]


class GitUnstageRequest(BaseModel):
    project_id: str
    paths: list[str]


class GitCommitRequest(BaseModel):
    project_id: str
    message: str


class GitProjectRequest(BaseModel):
    project_id: str


class GitStashRequest(BaseModel):
    project_id: str
    action: str = "push"


class GitDiscardRequest(BaseModel):
    project_id: str
    paths: list[str]


class GitSimpleResponse(BaseModel):
    success: bool
    error: str | None = None
```

- [ ] **Step 2: Verify syntax**

Run: `cd backend && python -c "from app.models.git import GitStatusResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/git.py
git commit -m "feat: add backend git pydantic models"
```

---

## Task 2: Backend Git Service

**Files:**
- Create: `backend/app/services/git_service.py`

- [ ] **Step 1: Create git service file**

```python
import asyncio
import logging
import os
from pathlib import Path

from app.errors import ValidationError
from app.security.path_security import PathSecurity
from app.services.project_service import project_service

logger = logging.getLogger(__name__)


class GitService:

    def _get_project_path(self, project_id: str) -> str:
        project = project_service.get_project_or_raise(project_id)
        return project.path

    def _make_security(self, project_path: str) -> PathSecurity:
        return PathSecurity(allowed_base_paths=[project_path], base_dir=project_path)

    async def _run_git(self, *args: str, cwd: str) -> tuple[int, str, str]:
        try:
            result = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            return (
                result.returncode,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except FileNotFoundError:
            raise ValidationError("git 命令不可用")

    def _validate_paths(self, paths: list[str], project_path: str) -> list[str]:
        security = self._make_security(project_path)
        validated = []
        for p in paths:
            try:
                validated.append(security.validate_path(p))
            except Exception as exc:
                raise ValidationError(str(exc)) from exc
        return validated

    async def get_status(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)

        rc, stdout, stderr = await self._run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=project_path)
        if rc != 0:
            raise ValidationError(f"不是 git 仓库: {stderr.strip()}")
        branch = stdout.strip()

        ahead = 0
        behind = 0
        rc, stdout, _ = await self._run_git(
            "rev-list", "--left-right", "--count", "@{upstream}...HEAD",
            cwd=project_path,
        )
        if rc == 0:
            parts = stdout.strip().split("\t")
            if len(parts) == 2:
                behind = int(parts[0])
                ahead = int(parts[1])

        rc, stdout, _ = await self._run_git("status", "--porcelain", cwd=project_path)
        staged = []
        unstaged = []
        untracked = []

        if rc == 0:
            for line in stdout.splitlines():
                if len(line) < 4:
                    continue
                x = line[0]
                y = line[1]
                filepath = line[3:].strip()

                if "R" in filepath:
                    arrow_idx = filepath.index(" -> ")
                    filepath = filepath[arrow_idx + 4:]

                if x in ("M", "A", "D", "R", "C"):
                    status = self._map_index_status(x)
                    staged.append({"path": filepath, "status": status})

                if y == "M":
                    unstaged.append({"path": filepath, "status": "M"})
                elif y == "D":
                    unstaged.append({"path": filepath, "status": "D"})

                if x == "?" and y == "?":
                    untracked.append({"path": filepath, "status": "U"})

        rc_cached, stdout_cached, _ = await self._run_git(
            "diff", "--cached", "--numstat", cwd=project_path
        )
        if rc_cached == 0:
            stat_map = self._parse_numstat(stdout_cached)
            for item in staged:
                stat = stat_map.get(item["path"])
                if stat:
                    item["insertions"] = stat[0]
                    item["deletions"] = stat[1]

        rc_uncached, stdout_uncached, _ = await self._run_git(
            "diff", "--numstat", cwd=project_path
        )
        if rc_uncached == 0:
            stat_map = self._parse_numstat(stdout_uncached)
            for item in unstaged:
                stat = stat_map.get(item["path"])
                if stat:
                    item["insertions"] = stat[0]
                    item["deletions"] = stat[1]

        return {
            "branch": branch,
            "ahead": ahead,
            "behind": behind,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        }

    def _map_index_status(self, code: str) -> str:
        mapping = {"M": "M", "A": "A", "D": "D", "R": "R", "C": "A"}
        return mapping.get(code, "M")

    def _parse_numstat(self, output: str) -> dict[str, tuple[int, int]]:
        result = {}
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                ins = int(parts[0]) if parts[0] != "-" else None
                dels = int(parts[1]) if parts[1] != "-" else None
                filepath = parts[2].strip()
                if ins is not None and dels is not None:
                    result[filepath] = (ins, dels)
        return result

    async def stage_files(self, project_id: str, paths: list[str]) -> dict:
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]
        rc, _, stderr = await self._run_git("add", *rel_paths, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git add 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def unstage_files(self, project_id: str, paths: list[str]) -> dict:
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]
        rc, _, stderr = await self._run_git("reset", "HEAD", "--", *rel_paths, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git reset 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def commit(self, project_id: str, message: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, _, stderr = await self._run_git("commit", "-m", message, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git commit 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def push(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("push", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        return {"success": True, "error": None}

    async def pull(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("pull", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        return {"success": True, "error": None}

    async def stash(self, project_id: str, action: str = "push") -> dict:
        project_path = self._get_project_path(project_id)
        if action == "pop":
            rc, _, stderr = await self._run_git("stash", "pop", cwd=project_path)
        else:
            rc, _, stderr = await self._run_git("stash", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip()}
        return {"success": True, "error": None}

    async def discard_changes(self, project_id: str, paths: list[str]) -> dict:
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]

        status_data = await self.get_status(project_id)
        untracked_paths = {item["path"] for item in status_data.get("untracked", [])}

        tracked = []
        to_delete = []
        for rp in rel_paths:
            if rp in untracked_paths:
                to_delete.append(rp)
            else:
                tracked.append(rp)

        if tracked:
            rc, _, stderr = await self._run_git("checkout", "--", *tracked, cwd=project_path)
            if rc != 0:
                raise ValidationError(f"git checkout 失败: {stderr.strip()}")

        for rp in to_delete:
            abs_path = os.path.join(project_path, rp)
            try:
                os.remove(abs_path)
            except OSError:
                pass

        return {"success": True, "error": None}


git_service = GitService()
```

- [ ] **Step 2: Verify syntax**

Run: `cd backend && python -c "from app.services.git_service import git_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/git_service.py
git commit -m "feat: add backend git service with status/stage/unstage/commit/push/pull/stash/discard"
```

---

## Task 3: Backend Git API Routes

**Files:**
- Create: `backend/app/api/routes/git.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create git routes file**

```python
from fastapi import APIRouter

from app.errors import value_error_to_app_error
from app.models.git import (
    GitCommitRequest,
    GitDiscardRequest,
    GitProjectRequest,
    GitSimpleResponse,
    GitStageRequest,
    GitStashRequest,
    GitStatusResponse,
    GitUnstageRequest,
)
from app.services.git_service import git_service

router = APIRouter(prefix="/api/git", tags=["git"])


@router.get("/status", response_model=GitStatusResponse)
async def get_git_status(project_id: str):
    try:
        return await git_service.get_status(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/stage", response_model=GitSimpleResponse)
async def stage_files(request: GitStageRequest):
    try:
        return await git_service.stage_files(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/unstage", response_model=GitSimpleResponse)
async def unstage_files(request: GitUnstageRequest):
    try:
        return await git_service.unstage_files(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/commit", response_model=GitSimpleResponse)
async def commit(request: GitCommitRequest):
    try:
        return await git_service.commit(request.project_id, request.message)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/push", response_model=GitSimpleResponse)
async def push(request: GitProjectRequest):
    return await git_service.push(request.project_id)


@router.post("/pull", response_model=GitSimpleResponse)
async def pull(request: GitProjectRequest):
    return await git_service.pull(request.project_id)


@router.post("/stash", response_model=GitSimpleResponse)
async def stash(request: GitStashRequest):
    return await git_service.stash(request.project_id, request.action)


@router.post("/discard", response_model=GitSimpleResponse)
async def discard_changes(request: GitDiscardRequest):
    try:
        return await git_service.discard_changes(request.project_id, request.paths)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc
```

- [ ] **Step 2: Register git router in main.py**

Add to `backend/app/main.py`:
- In imports: add `git` to the routes import line
- After `app.include_router(files.router)`: add `app.include_router(git.router)`

The import line becomes:
```python
from app.api.routes import files, git, llm, projects, sessions, skills, websocket
```

Add after `app.include_router(files.router)`:
```python
app.include_router(git.router)
```

- [ ] **Step 3: Verify server starts**

Run: `cd backend && python -c "from app.main import app; print('Routes:', [r.path for r in app.routes if hasattr(r, 'path') and '/api/git/' in r.path])"`
Expected: List of git API paths

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/git.py backend/app/main.py
git commit -m "feat: add backend git API routes and register in main"
```

---

## Task 4: Frontend Git Types

**Files:**
- Create: `frontend/src/types/git.ts`

- [ ] **Step 1: Create git types file**

```typescript
export type GitStatusCode = 'M' | 'A' | 'D' | 'U' | 'R'

export interface GitFileChange {
  path: string
  status: GitStatusCode
  insertions?: number | null
  deletions?: number | null
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

export interface GitSimpleResponse {
  success: boolean
  error: string | null
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit src/types/git.ts 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/git.ts
git commit -m "feat: add frontend git TypeScript types"
```

---

## Task 5: Frontend Git API Client

**Files:**
- Create: `frontend/src/features/git/gitApi.ts`

- [ ] **Step 1: Create git API client**

```typescript
import { apiClient } from '@/services/apiClient'
import type { GitStatusResponse, GitSimpleResponse } from '@/types/git'

export const gitApi = {
  getStatus: (projectId: string) =>
    apiClient.get<GitStatusResponse>('/api/git/status', {
      params: { project_id: projectId },
    }),

  stageFiles: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/stage', {
      project_id: projectId,
      paths,
    }),

  unstageFiles: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/unstage', {
      project_id: projectId,
      paths,
    }),

  commit: (projectId: string, message: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/commit', {
      project_id: projectId,
      message,
    }),

  push: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/push', {
      project_id: projectId,
    }),

  pull: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/pull', {
      project_id: projectId,
    }),

  stash: (projectId: string, action: 'push' | 'pop') =>
    apiClient.post<GitSimpleResponse>('/api/git/stash', {
      project_id: projectId,
      action,
    }),

  discardChanges: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/discard', {
      project_id: projectId,
      paths,
    }),
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit src/features/git/gitApi.ts 2>&1 | head -5`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/git/gitApi.ts
git commit -m "feat: add frontend git API client"
```

---

## Task 6: Frontend Git Store

**Files:**
- Create: `frontend/src/features/git/gitStore.ts`

- [ ] **Step 1: Create git Zustand store**

```typescript
import { create } from 'zustand'
import { gitApi } from '@/features/git/gitApi'
import { useProjectStore } from '@/stores/projectStore'
import type { GitFileChange, GitBranchInfo } from '@/types/git'

type SidebarTab = 'files' | 'changes'

interface GitState {
  branchInfo: GitBranchInfo | null
  stagedFiles: GitFileChange[]
  unstagedFiles: GitFileChange[]
  untrackedFiles: GitFileChange[]
  sidebarTab: SidebarTab
  stagedCollapsed: boolean
  unstagedCollapsed: boolean
  commitMessage: string
  isLoading: boolean
  isCommitting: boolean
  isPushing: boolean
  isPulling: boolean

  totalChanges: () => number

  fetchStatus: () => Promise<void>
  stageFiles: (paths: string[]) => Promise<void>
  unstageFiles: (paths: string[]) => Promise<void>
  commit: (message: string) => Promise<void>
  push: () => Promise<void>
  pull: () => Promise<void>
  stash: (action: 'push' | 'pop') => Promise<void>
  discardChanges: (paths: string[]) => Promise<void>
  setSidebarTab: (tab: SidebarTab) => void
  setCommitMessage: (msg: string) => void
  toggleStagedCollapsed: () => void
  toggleUnstagedCollapsed: () => void
}

function _getProjectId(): string | null {
  return useProjectStore.getState().currentProject?.id ?? null
}

export const useGitStore = create<GitState>()((set, get) => ({
  branchInfo: null,
  stagedFiles: [],
  unstagedFiles: [],
  untrackedFiles: [],
  sidebarTab: 'files',
  stagedCollapsed: false,
  unstagedCollapsed: false,
  commitMessage: '',
  isLoading: false,
  isCommitting: false,
  isPushing: false,
  isPulling: false,

  totalChanges: () => {
    const s = get()
    return s.stagedFiles.length + s.unstagedFiles.length + s.untrackedFiles.length
  },

  fetchStatus: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isLoading: true })
    try {
      const resp = await gitApi.getStatus(projectId)
      const data = resp.data
      set({
        branchInfo: { name: data.branch, ahead: data.ahead, behind: data.behind },
        stagedFiles: data.staged,
        unstagedFiles: data.unstaged,
        untrackedFiles: data.untracked,
        isLoading: false,
      })
    } catch {
      set({ isLoading: false })
    }
  },

  stageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.stageFiles(projectId, paths)
    await get().fetchStatus()
  },

  unstageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.unstageFiles(projectId, paths)
    await get().fetchStatus()
  },

  commit: async (message) => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isCommitting: true })
    try {
      await gitApi.commit(projectId, message)
      set({ commitMessage: '', isCommitting: false })
      await get().fetchStatus()
    } catch {
      set({ isCommitting: false })
    }
  },

  push: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPushing: true })
    try {
      await gitApi.push(projectId)
      set({ isPushing: false })
      await get().fetchStatus()
    } catch {
      set({ isPushing: false })
    }
  },

  pull: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPulling: true })
    try {
      await gitApi.pull(projectId)
      set({ isPulling: false })
      await get().fetchStatus()
    } catch {
      set({ isPulling: false })
    }
  },

  stash: async (action) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.stash(projectId, action)
    await get().fetchStatus()
  },

  discardChanges: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.discardChanges(projectId, paths)
    await get().fetchStatus()
  },

  setSidebarTab: (tab) => {
    set({ sidebarTab: tab })
    if (tab === 'changes') {
      get().fetchStatus()
    }
  },

  setCommitMessage: (msg) => set({ commitMessage: msg }),
  toggleStagedCollapsed: () => set((s) => ({ stagedCollapsed: !s.stagedCollapsed })),
  toggleUnstagedCollapsed: () => set((s) => ({ unstagedCollapsed: !s.unstagedCollapsed })),
}))
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to gitStore

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/git/gitStore.ts
git commit -m "feat: add frontend git Zustand store"
```

---

## Task 7: Frontend Git Components — GitBranchBar

**Files:**
- Create: `frontend/src/components/workspace/git/GitBranchBar.tsx`

- [ ] **Step 1: Create GitBranchBar component**

```tsx
import { GitBranch, ArrowUp, ArrowDown } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'

export function GitBranchBar() {
  const branchInfo = useGitStore((s) => s.branchInfo)

  if (!branchInfo) return null

  return (
    <div className="flex items-center gap-2 border-b border-edge-subtle px-3 py-2 text-xs text-content-secondary">
      <GitBranch className="h-3.5 w-3.5 shrink-0 text-content-muted" />
      <span className="truncate font-medium">{branchInfo.name}</span>
      {(branchInfo.ahead > 0 || branchInfo.behind > 0) && (
        <span className="ml-auto flex items-center gap-1 text-content-muted">
          {branchInfo.ahead > 0 && (
            <span className="flex items-center gap-0.5">
              <ArrowUp className="h-3 w-3" />
              {branchInfo.ahead}
            </span>
          )}
          {branchInfo.behind > 0 && (
            <span className="flex items-center gap-0.5">
              <ArrowDown className="h-3 w-3" />
              {branchInfo.behind}
            </span>
          )}
        </span>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/git/GitBranchBar.tsx
git commit -m "feat: add GitBranchBar component"
```

---

## Task 8: Frontend Git Components — GitFileItem

**Files:**
- Create: `frontend/src/components/workspace/git/GitFileItem.tsx`

- [ ] **Step 1: Create GitFileItem component**

```tsx
import { File, Plus, Minus, RotateCcw } from 'lucide-react'
import type { GitStatusCode } from '@/types/git'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { useGitStore } from '@/features/git/gitStore'
import { useToast } from '@/hooks/useToast'

const GIT_STATUS_STYLES: Record<GitStatusCode, string> = {
  M: 'text-status-success',
  A: 'text-status-success',
  D: 'text-status-error',
  U: 'text-content-muted',
  R: 'text-accent',
}

interface GitFileItemProps {
  path: string
  status: GitStatusCode
  insertions?: number | null
  deletions?: number | null
  section: 'staged' | 'unstaged' | 'untracked'
}

export function GitFileItem({ path, status, insertions, deletions, section }: GitFileItemProps) {
  const setActiveFile = useCodeTabStore((s) => s.setActiveFile)
  const stageFiles = useGitStore((s) => s.stageFiles)
  const unstageFiles = useGitStore((s) => s.unstageFiles)
  const discardChanges = useGitStore((s) => s.discardChanges)
  const addToast = useToast()

  const filename = path.split('/').pop() ?? path

  const handleOpenFile = () => {
    setActiveFile(path, '')
  }

  const handleStage = () => {
    stageFiles([path])
  }

  const handleUnstage = () => {
    unstageFiles([path])
  }

  const handleDiscard = async () => {
    discardChanges([path])
    addToast('已丢弃变更: ' + filename, 'info')
  }

  return (
    <div className="group flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-surface-tertiary">
      <File className="h-3.5 w-3.5 shrink-0 text-content-muted" />
      <button
        type="button"
        onClick={handleOpenFile}
        className="flex-1 truncate text-left text-sm text-content-secondary hover:text-content-primary"
        title={path}
      >
        {filename}
      </button>
      {(insertions != null || deletions != null) && (
        <span className="text-xs text-content-muted">
          {insertions != null && <span className="text-status-success">+{insertions}</span>}
          {deletions != null && <span className="text-status-error">-{deletions}</span>}
        </span>
      )}
      <span className={`text-xs font-mono ${GIT_STATUS_STYLES[status]}`}>{status}</span>
      {section === 'staged' && (
        <button
          type="button"
          onClick={handleUnstage}
          className="rounded p-0.5 text-content-muted opacity-0 group-hover:opacity-100 hover:text-content-primary hover:bg-surface-tertiary"
          title="Unstage"
        >
          <Minus className="h-3 w-3" />
        </button>
      )}
      {(section === 'unstaged' || section === 'untracked') && (
        <>
          <button
            type="button"
            onClick={handleStage}
            className="rounded p-0.5 text-content-muted opacity-0 group-hover:opacity-100 hover:text-content-primary hover:bg-surface-tertiary"
            title="Stage"
          >
            <Plus className="h-3 w-3" />
          </button>
          <button
            type="button"
            onClick={handleDiscard}
            className="rounded p-0.5 text-content-muted opacity-0 group-hover:opacity-100 hover:text-status-error hover:bg-surface-tertiary"
            title="丢弃变更"
          >
            <RotateCcw className="h-3 w-3" />
          </button>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/git/GitFileItem.tsx
git commit -m "feat: add GitFileItem component with stage/unstage/discard"
```

---

## Task 9: Frontend Git Components — GitFileGroup

**Files:**
- Create: `frontend/src/components/workspace/git/GitFileGroup.tsx`

- [ ] **Step 1: Create GitFileGroup component**

```tsx
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { GitFileChange, GitStatusCode } from '@/types/git'
import { GitFileItem } from './GitFileItem'

interface GitFileGroupProps {
  title: string
  files: GitFileChange[]
  section: 'staged' | 'unstaged' | 'untracked'
  collapsed: boolean
  onToggleCollapsed: () => void
}

export function GitFileGroup({ title, files, section, collapsed, onToggleCollapsed }: GitFileGroupProps) {
  if (files.length === 0) return null

  return (
    <div className="border-b border-edge-subtle">
      <button
        type="button"
        onClick={onToggleCollapsed}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-surface-tertiary"
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3 shrink-0 text-content-muted" />
        ) : (
          <ChevronDown className="h-3 w-3 shrink-0 text-content-muted" />
        )}
        <span>{title}</span>
        <span className="ml-1 text-content-muted">({files.length})</span>
      </button>
      {!collapsed && (
        <div className="pb-1">
          {files.map((file) => (
            <GitFileItem
              key={file.path}
              path={file.path}
              status={file.status as GitStatusCode}
              insertions={file.insertions}
              deletions={file.deletions}
              section={section}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/git/GitFileGroup.tsx
git commit -m "feat: add GitFileGroup collapsible section component"
```

---

## Task 10: Frontend Git Components — GitCommitInput

**Files:**
- Create: `frontend/src/components/workspace/git/GitCommitInput.tsx`

- [ ] **Step 1: Create GitCommitInput component**

```tsx
import { Check } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'

export function GitCommitInput() {
  const commitMessage = useGitStore((s) => s.commitMessage)
  const setCommitMessage = useGitStore((s) => s.setCommitMessage)
  const commit = useGitStore((s) => s.commit)
  const stagedFiles = useGitStore((s) => s.stagedFiles)
  const isCommitting = useGitStore((s) => s.isCommitting)

  const canCommit = stagedFiles.length > 0 && commitMessage.trim().length > 0 && !isCommitting

  const handleCommit = () => {
    if (!canCommit) return
    commit(commitMessage.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && canCommit) {
      e.preventDefault()
      handleCommit()
    }
  }

  return (
    <div className="border-b border-edge-subtle px-3 py-2">
      <textarea
        value={commitMessage}
        onChange={(e) => setCommitMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Commit message..."
        rows={2}
        className="w-full resize-none rounded-md border border-edge-subtle bg-surface-primary px-2 py-1.5 text-sm text-content-primary placeholder:text-content-muted focus:border-accent focus:outline-none"
      />
      <button
        type="button"
        onClick={handleCommit}
        disabled={!canCommit}
        className={`mt-1.5 flex w-full items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          canCommit
            ? 'bg-accent text-white hover:bg-accent-hover'
            : 'bg-surface-tertiary text-content-muted cursor-not-allowed'
        }`}
      >
        <Check className="h-3.5 w-3.5" />
        {isCommitting ? '提交中...' : 'Commit'}
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/git/GitCommitInput.tsx
git commit -m "feat: add GitCommitInput component"
```

---

## Task 11: Frontend Git Components — GitActionBar

**Files:**
- Create: `frontend/src/components/workspace/git/GitActionBar.tsx`

- [ ] **Step 1: Create GitActionBar component**

```tsx
import { ArrowUp, ArrowDown, Archive, ArchiveRestore } from 'lucide-react'
import { useGitStore } from '@/features/git/gitStore'
import { useState } from 'react'

export function GitActionBar() {
  const push = useGitStore((s) => s.push)
  const pull = useGitStore((s) => s.pull)
  const stash = useGitStore((s) => s.stash)
  const isPushing = useGitStore((s) => s.isPushing)
  const isPulling = useGitStore((s) => s.isPulling)
  const [showStashPop, setShowStashPop] = useState(false)

  return (
    <div className="flex items-center gap-1 px-3 py-2">
      <button
        type="button"
        onClick={() => push()}
        disabled={isPushing}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-50"
        title="Push"
      >
        <ArrowUp className="h-3.5 w-3.5" />
        {isPushing ? '...' : 'Push'}
      </button>
      <button
        type="button"
        onClick={() => pull()}
        disabled={isPulling}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary disabled:opacity-50"
        title="Pull"
      >
        <ArrowDown className="h-3.5 w-3.5" />
        {isPulling ? '...' : 'Pull'}
      </button>
      <div className="relative">
        <button
          type="button"
          onClick={() => {
            if (showStashPop) {
              stash('pop')
              setShowStashPop(false)
            } else {
              stash('push')
            }
          }}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-content-secondary hover:bg-surface-tertiary hover:text-content-primary"
          title="Stash"
        >
          <Archive className="h-3.5 w-3.5" />
          Stash
        </button>
        <button
          type="button"
          onClick={() => setShowStashPop(!showStashPop)}
          className="ml-0.5 rounded p-0.5 text-content-muted hover:text-content-primary hover:bg-surface-tertiary"
          title="Stash Pop"
        >
          <ArchiveRestore className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/git/GitActionBar.tsx
git commit -m "feat: add GitActionBar component with push/pull/stash"
```

---

## Task 12: Frontend Git Components — GitChangesTab

**Files:**
- Create: `frontend/src/components/workspace/git/GitChangesTab.tsx`

- [ ] **Step 1: Create GitChangesTab container component**

```tsx
import { useGitStore } from '@/features/git/gitStore'
import { GitBranchBar } from './GitBranchBar'
import { GitFileGroup } from './GitFileGroup'
import { GitCommitInput } from './GitCommitInput'
import { GitActionBar } from './GitActionBar'

export function GitChangesTab() {
  const branchInfo = useGitStore((s) => s.branchInfo)
  const stagedFiles = useGitStore((s) => s.stagedFiles)
  const unstagedFiles = useGitStore((s) => s.unstagedFiles)
  const untrackedFiles = useGitStore((s) => s.untrackedFiles)
  const stagedCollapsed = useGitStore((s) => s.stagedCollapsed)
  const unstagedCollapsed = useGitStore((s) => s.unstagedCollapsed)
  const toggleStagedCollapsed = useGitStore((s) => s.toggleStagedCollapsed)
  const toggleUnstagedCollapsed = useGitStore((s) => s.toggleUnstagedCollapsed)
  const isLoading = useGitStore((s) => s.isLoading)

  const allUnstaged = [...unstagedFiles, ...untrackedFiles]

  if (isLoading && !branchInfo) {
    return (
      <div className="flex-1 px-3 py-4 text-xs text-content-muted">
        加载中...
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <GitBranchBar />
      <GitFileGroup
        title="Staged Changes"
        files={stagedFiles}
        section="staged"
        collapsed={stagedCollapsed}
        onToggleCollapsed={toggleStagedCollapsed}
      />
      <GitFileGroup
        title="Changes"
        files={allUnstaged}
        section="unstaged"
        collapsed={unstagedCollapsed}
        onToggleCollapsed={toggleUnstagedCollapsed}
      />
      <GitCommitInput />
      <GitActionBar />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/git/GitChangesTab.tsx
git commit -m "feat: add GitChangesTab container component"
```

---

## Task 13: Modify FileSidebar — Add Tab Switcher

**Files:**
- Modify: `frontend/src/components/workspace/FileSidebar.tsx`
- Modify: `frontend/src/features/code/codeTabStore.ts`

- [ ] **Step 1: Add sidebarTab to codeTabStore**

In `frontend/src/features/code/codeTabStore.ts`, add `sidebarTab` state and action:

Add to `CodeTabState` interface:
```typescript
sidebarTab: 'files' | 'changes'
```

Add to `CodeTabActions` interface:
```typescript
setSidebarTab: (tab: 'files' | 'changes') => void
```

Add to the store creation (after `expandedDirs: {}`):
```typescript
sidebarTab: 'files',
```

Add action (after `setDirExpanded`):
```typescript
setSidebarTab: (tab) => set({ sidebarTab: tab }),
```

- [ ] **Step 2: Modify FileSidebar to add tab switcher and render GitChangesTab**

Replace the entire content of `frontend/src/components/workspace/FileSidebar.tsx` with:

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { GripVertical, PanelRightClose, RefreshCw } from 'lucide-react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { useGitStore } from '@/features/git/gitStore'
import { fileApi } from '@/features/code/fileApi'
import { useProjectStore } from '@/stores/projectStore'
import { FileTreeItem } from './FileTreeItem'
import { GitChangesTab } from './git/GitChangesTab'
import type { FileTreeNode } from '@/types/fileTree'

export function FileSidebar() {
  const sidebarOpen = useCodeTabStore((s) => s.sidebarOpen)
  const sidebarWidth = useCodeTabStore((s) => s.sidebarWidth)
  const setSidebarOpen = useCodeTabStore((s) => s.setSidebarOpen)
  const setSidebarWidth = useCodeTabStore((s) => s.setSidebarWidth)
  const sidebarTab = useCodeTabStore((s) => s.sidebarTab)
  const setSidebarTab = useCodeTabStore((s) => s.setSidebarTab)
  const currentProject = useProjectStore((s) => s.currentProject)
  const totalChanges = useGitStore((s) => s.totalChanges)

  const [tree, setTree] = useState<FileTreeNode[]>([])
  const [loading, setLoading] = useState(false)
  const resizingRef = useRef(false)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)

  useEffect(() => {
    if (!currentProject || !sidebarOpen) return
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        const resp = await fileApi.getTree(currentProject!.id)
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
  }, [currentProject, sidebarOpen])

  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizingRef.current = true
    startXRef.current = e.clientX
    startWidthRef.current = sidebarWidth

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!resizingRef.current) return
      const delta = startXRef.current - moveEvent.clientX
      setSidebarWidth(startWidthRef.current - delta)
    }

    const onMouseUp = () => {
      resizingRef.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [sidebarWidth, setSidebarWidth])

  if (!sidebarOpen) return null

  const changesCount = totalChanges()

  return (
    <div className="relative flex h-full flex-col border-l border-edge bg-surface-primary" style={{ width: sidebarWidth }}>
      <div className="flex items-center justify-between border-b border-edge-subtle px-3 py-2">
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
            className="rounded-md p-1 text-content-muted hover:bg-surface-tertiary hover:text-content-secondary"
            title="刷新"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="rounded-md p-1 text-content-muted hover:bg-surface-tertiary hover:text-content-secondary"
            title="收起文件栏"
          >
            <PanelRightClose className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="flex border-b border-edge-subtle">
        <button
          type="button"
          onClick={() => setSidebarTab('files')}
          className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
            sidebarTab === 'files'
              ? 'text-content-primary border-b-2 border-accent'
              : 'text-content-muted hover:text-content-secondary'
          }`}
        >
          文件
        </button>
        <button
          type="button"
          onClick={() => setSidebarTab('changes')}
          className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
            sidebarTab === 'changes'
              ? 'text-content-primary border-b-2 border-accent'
              : 'text-content-muted hover:text-content-secondary'
          }`}
        >
          变更{changesCount > 0 ? ` ${changesCount}` : ''}
        </button>
      </div>

      {sidebarTab === 'files' ? (
        <div className="flex-1 overflow-y-auto py-1">
          {!currentProject ? (
            <div className="px-3 py-4 text-xs text-content-muted">请先选择项目</div>
          ) : loading ? (
            <div className="px-3 py-4 text-xs text-content-muted">加载中...</div>
          ) : (
            tree.map((node) => (
              <FileTreeItem key={node.path} node={node} depth={0} />
            ))
          )}
        </div>
      ) : (
        <GitChangesTab />
      )}

      <div
        onMouseDown={handleResizeMouseDown}
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize group"
        title="拖拽调整宽度"
      >
        <div className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-sm bg-transparent p-0.5 opacity-0 group-hover:opacity-100 group-hover:bg-surface-tertiary transition-opacity">
          <GripVertical className="h-3 w-3 text-slate-400" />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/workspace/FileSidebar.tsx frontend/src/features/code/codeTabStore.ts
git commit -m "feat: add tab switcher to FileSidebar with Files/Changes tabs"
```

---

## Task 14: Update GitFileItem section handling for untracked files

**Files:**
- Modify: `frontend/src/components/workspace/git/GitFileGroup.tsx`

The GitChangesTab combines unstaged + untracked into one group but passes `section="unstaged"` for all. Untracked files need `section="untracked"` for the correct stage/discard buttons.

- [ ] **Step 1: Update GitChangesTab to split untracked into separate group**

Replace `frontend/src/components/workspace/git/GitChangesTab.tsx` content:

```tsx
import { useGitStore } from '@/features/git/gitStore'
import { GitBranchBar } from './GitBranchBar'
import { GitFileGroup } from './GitFileGroup'
import { GitCommitInput } from './GitCommitInput'
import { GitActionBar } from './GitActionBar'

export function GitChangesTab() {
  const branchInfo = useGitStore((s) => s.branchInfo)
  const stagedFiles = useGitStore((s) => s.stagedFiles)
  const unstagedFiles = useGitStore((s) => s.unstagedFiles)
  const untrackedFiles = useGitStore((s) => s.untrackedFiles)
  const stagedCollapsed = useGitStore((s) => s.stagedCollapsed)
  const unstagedCollapsed = useGitStore((s) => s.unstagedCollapsed)
  const toggleStagedCollapsed = useGitStore((s) => s.toggleStagedCollapsed)
  const toggleUnstagedCollapsed = useGitStore((s) => s.toggleUnstagedCollapsed)
  const isLoading = useGitStore((s) => s.isLoading)

  if (isLoading && !branchInfo) {
    return (
      <div className="flex-1 px-3 py-4 text-xs text-content-muted">
        加载中...
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <GitBranchBar />
      <GitFileGroup
        title="Staged Changes"
        files={stagedFiles}
        section="staged"
        collapsed={stagedCollapsed}
        onToggleCollapsed={toggleStagedCollapsed}
      />
      <GitFileGroup
        title="Changes"
        files={unstagedFiles}
        section="unstaged"
        collapsed={unstagedCollapsed}
        onToggleCollapsed={toggleUnstagedCollapsed}
      />
      <GitFileGroup
        title="Untracked"
        files={untrackedFiles}
        section="untracked"
        collapsed={false}
        onToggleCollapsed={() => {}}
      />
      <GitCommitInput />
      <GitActionBar />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/workspace/git/GitChangesTab.tsx
git commit -m "fix: separate untracked files into their own group in Changes tab"
```

---

## Task 15: Integration Verification

- [ ] **Step 1: Start backend and verify git API works**

Run: `cd backend && python -c "from app.main import app; routes = [r.path for r in app.routes if hasattr(r, 'path')]; git_routes = [r for r in routes if '/api/git' in r]; print('Git routes:', git_routes)"`

Expected: All 8 git routes listed

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | tail -5`

Expected: No errors

- [ ] **Step 3: Verify frontend dev server starts**

Run: `cd frontend && npx vite build 2>&1 | tail -5`

Expected: Build succeeds

- [ ] **Step 4: Final commit if any fixes needed**

If any issues found during verification, fix and commit with appropriate message.
