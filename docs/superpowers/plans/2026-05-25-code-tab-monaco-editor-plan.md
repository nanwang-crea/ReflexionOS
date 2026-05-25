# Code Tab with Monaco Editor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Chat/Code full-screen tab switcher to the workspace, with a Monaco-based diff viewer and code editor triggered by clicking file-related receipts in the chat.

**Architecture:** New backend file API routes provide file content, git diff content, and file write. New frontend Zustand store manages Code tab state. Monaco Editor renders diff (read-only, side-by-side) and edit (writable, single-pane) views. Receipt click in chat auto-switches to Code tab with the right file and sub-tab.

**Tech Stack:** `@monaco-editor/react` (Monaco), FastAPI (backend), Zustand (state), React + TypeScript + TailwindCSS (UI)

---

## File Structure

### New Files

| File | Responsibility |
|------|----------------|
| `backend/app/api/routes/files.py` | API routes: file content, diff content, file write |
| `backend/app/services/file_content_service.py` | Business logic: read file, compute git diff, write file |
| `backend/app/models/file_content.py` | Pydantic models for file content / diff / write requests and responses |
| `frontend/src/features/code/fileApi.ts` | API client calls for the 3 new endpoints |
| `frontend/src/features/code/codeTabStore.ts` | Zustand store for Code tab state |
| `frontend/src/components/workspace/CodeTab.tsx` | Code tab container — sub-tab switching, file loading |
| `frontend/src/components/workspace/DiffViewer.tsx` | Monaco DiffEditor wrapper (read-only) |
| `frontend/src/components/workspace/CodeEditor.tsx` | Monaco Editor wrapper (editable) |
| `frontend/src/components/workspace/CodeTabBar.tsx` | Sub-tab bar: [Diff] [Edit] + filename + save button |
| `frontend/src/types/file.ts` | TypeScript types for file content / diff / write responses |
| `backend/tests/test_file_content_api.py` | Integration tests for the 3 new API endpoints |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/main.py` | Register new `files` router |
| `frontend/src/pages/AgentWorkspace.tsx` | Add Chat/Code tab bar, render CodeTab when Code tab active |
| `frontend/src/components/workspace/WorkspaceHeader.tsx` | Integrate tab bar into header row |
| `frontend/src/components/execution/ActionReceipt.tsx` | Make edit/create/delete receipt rows clickable |
| `frontend/src/components/execution/receiptUtils.ts` | Export `target` path from `ActionReceiptDetail` (already present) |
| `frontend/package.json` | Add `@monaco-editor/react` dependency |

---

### Task 1: Backend — Pydantic Models for File Content API

**Files:**
- Create: `backend/app/models/file_content.py`
- Test: `backend/tests/test_file_content_api.py` (types validated in Task 3)

- [ ] **Step 1: Create the Pydantic model file**

```python
from pydantic import BaseModel, ConfigDict


class FileContentResponse(BaseModel):
    content: str
    language: str
    exists: bool


class FileDiffContentResponse(BaseModel):
    original: str
    modified: str
    language: str


class FileWriteRequest(BaseModel):
    project_id: str
    path: str
    content: str


class FileWriteResponse(BaseModel):
    success: bool
    error: str | None = None
```

- [ ] **Step 2: Verify the models import correctly**

Run: `cd backend && python -c "from app.models.file_content import FileContentResponse, FileDiffContentResponse, FileWriteRequest, FileWriteResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/file_content.py
git commit -m "feat: add Pydantic models for file content API"
```

---

### Task 2: Backend — File Content Service

**Files:**
- Create: `backend/app/services/file_content_service.py`

- [ ] **Step 1: Create the service**

```python
import asyncio
import logging
import os
import subprocess
from pathlib import Path

from app.errors import NotFoundValueError, SecurityError, ValidationError
from app.security.path_security import PathSecurity
from app.services.project_service import project_service

logger = logging.getLogger(__name__)

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".sh": "shell",
    ".sql": "sql",
    ".xml": "xml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".lua": "lua",
    ".r": "r",
    ".dart": "dart",
}


def _infer_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "plaintext")


class FileContentService:
    """文件内容读取与写入服务"""

    def __init__(self) -> None:
        pass

    def _get_project_path(self, project_id: str) -> str:
        project = project_service.get_project_or_raise(project_id)
        return project.path

    def _make_security(self, project_path: str) -> PathSecurity:
        return PathSecurity(allowed_base_paths=[project_path], base_dir=project_path)

    async def get_file_content(self, project_id: str, path: str) -> dict:
        project_path = self._get_project_path(project_id)
        security = self._make_security(project_path)

        try:
            validated_path = security.validate_path(path)
        except SecurityError as exc:
            raise ValidationError(str(exc)) from exc

        abs_path = Path(validated_path)
        if not abs_path.exists() or not abs_path.is_file():
            return {
                "content": "",
                "language": _infer_language(path),
                "exists": False,
            }

        try:
            content = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValidationError("文件编码不支持，仅支持 UTF-8 文本文件")
        except OSError as exc:
            raise ValidationError(f"读取文件失败: {exc}")

        return {
            "content": content,
            "language": _infer_language(path),
            "exists": True,
        }

    async def get_diff_content(self, project_id: str, path: str) -> dict:
        project_path = self._get_project_path(project_id)
        security = self._make_security(project_path)

        try:
            validated_path = security.validate_path(path)
        except SecurityError as exc:
            raise ValidationError(str(exc)) from exc

        abs_path = Path(validated_path)
        original = ""
        modified = ""

        # Get original from git HEAD
        relative_path = os.path.relpath(validated_path, project_path)
        try:
            result = await asyncio.create_subprocess_exec(
                "git", "show", f"HEAD:{relative_path}",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            if result.returncode == 0:
                original = stdout.decode("utf-8", errors="replace")
            else:
                # File not in HEAD (new file or not tracked)
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.debug("git show HEAD:%s failed: %s", relative_path, err_msg)
                original = ""
        except FileNotFoundError:
            raise ValidationError("git 命令不可用，无法获取 diff")

        # Get modified from disk
        if abs_path.exists() and abs_path.is_file():
            try:
                modified = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise ValidationError("文件编码不支持，仅支持 UTF-8 文本文件")
            except OSError as exc:
                raise ValidationError(f"读取文件失败: {exc}")

        return {
            "original": original,
            "modified": modified,
            "language": _infer_language(path),
        }

    async def write_file_content(self, project_id: str, path: str, content: str) -> dict:
        project_path = self._get_project_path(project_id)
        security = self._make_security(project_path)

        try:
            validated_path = security.validate_write_path(path)
        except SecurityError as exc:
            raise ValidationError(str(exc)) from exc

        abs_path = Path(validated_path)
        dir_path = abs_path.parent
        if dir_path and not dir_path.exists():
            os.makedirs(dir_path, exist_ok=True)

        try:
            abs_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return {"success": False, "error": f"写入文件失败: {exc}"}

        logger.info("写入文件: %s", validated_path)
        return {"success": True, "error": None}


file_content_service = FileContentService()
```

- [ ] **Step 2: Verify service imports**

Run: `cd backend && python -c "from app.services.file_content_service import file_content_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/file_content_service.py
git commit -m "feat: add FileContentService with git diff support"
```

---

### Task 3: Backend — File Content API Routes

**Files:**
- Create: `backend/app/api/routes/files.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_file_content_api.py`

- [ ] **Step 1: Create the API routes file**

```python
from fastapi import APIRouter, Query

from app.errors import value_error_to_app_error
from app.models.file_content import (
    FileContentResponse,
    FileDiffContentResponse,
    FileWriteRequest,
    FileWriteResponse,
)
from app.services.file_content_service import file_content_service

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/content", response_model=FileContentResponse)
async def get_file_content(
    project_id: str = Query(..., description="项目 ID"),
    path: str = Query(..., description="文件路径"),
):
    try:
        return await file_content_service.get_file_content(project_id, path)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.get("/diff-content", response_model=FileDiffContentResponse)
async def get_diff_content(
    project_id: str = Query(..., description="项目 ID"),
    path: str = Query(..., description="文件路径"),
):
    try:
        return await file_content_service.get_diff_content(project_id, path)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc


@router.post("/write", response_model=FileWriteResponse)
async def write_file_content(request: FileWriteRequest):
    try:
        return await file_content_service.write_file_content(
            request.project_id, request.path, request.content
        )
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="项目") from exc
```

- [ ] **Step 2: Register the router in main.py**

Add import and include_router to `backend/app/main.py`:

In the imports section (after line 7), add:
```python
from app.api.routes import files
```

After line 51 (`app.include_router(websocket.router)`), add:
```python
app.include_router(files.router)
```

- [ ] **Step 3: Create the integration test file**

```python
import os
import subprocess
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def git_project():
    """Create a temporary git repo with a test file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Init git repo
        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmpdir, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmpdir, check=True, capture_output=True,
        )

        # Create and commit a file
        file_path = os.path.join(tmpdir, "example.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=tmpdir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmpdir, check=True, capture_output=True,
        )

        # Create project via API
        yield tmpdir


def _create_project(client, path):
    resp = client.post("/api/projects", json={"name": "test", "path": path})
    assert resp.status_code == 200
    return resp.json()["id"]


class TestFileContentAPI:
    def test_get_file_content_existing(self, client, git_project):
        project_id = _create_project(client, git_project)
        resp = client.get("/api/files/content", params={"project_id": project_id, "path": "example.py"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert "def hello()" in data["content"]
        assert data["language"] == "python"

    def test_get_file_content_nonexistent(self, client, git_project):
        project_id = _create_project(client, git_project)
        resp = client.get("/api/files/content", params={"project_id": project_id, "path": "nope.py"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["content"] == ""

    def test_get_file_content_path_traversal_blocked(self, client, git_project):
        project_id = _create_project(client, git_project)
        resp = client.get("/api/files/content", params={"project_id": project_id, "path": "../etc/passwd"})
        assert resp.status_code in (400, 403)

    def test_get_diff_content_modified_file(self, client, git_project):
        project_id = _create_project(client, git_project)

        # Modify the file
        file_path = os.path.join(git_project, "example.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'changed'\n")

        resp = client.get("/api/files/diff-content", params={"project_id": project_id, "path": "example.py"})
        assert resp.status_code == 200
        data = resp.json()
        assert "'world'" in data["original"]
        assert "'changed'" in data["modified"]
        assert data["language"] == "python"

    def test_get_diff_content_new_file(self, client, git_project):
        project_id = _create_project(client, git_project)

        # Create a new untracked file
        new_file = os.path.join(git_project, "new.ts")
        with open(new_file, "w", encoding="utf-8") as f:
            f.write("const x = 1;\n")

        resp = client.get("/api/files/diff-content", params={"project_id": project_id, "path": "new.ts"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["original"] == ""
        assert "const x = 1" in data["modified"]
        assert data["language"] == "typescript"

    def test_write_file_content(self, client, git_project):
        project_id = _create_project(client, git_project)
        resp = client.post("/api/files/write", json={
            "project_id": project_id,
            "path": "written.py",
            "content": "print('hello')\n",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Verify file was written
        file_path = os.path.join(git_project, "written.py")
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == "print('hello')\n"

    def test_write_file_content_sensitive_blocked(self, client, git_project):
        project_id = _create_project(client, git_project)
        resp = client.post("/api/files/write", json={
            "project_id": project_id,
            "path": ".env",
            "content": "SECRET=abc\n",
        })
        assert resp.status_code in (400, 403)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_file_content_api.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/files.py backend/app/main.py backend/tests/test_file_content_api.py
git commit -m "feat: add file content, diff, and write API endpoints"
```

---

### Task 4: Frontend — Install Monaco Editor Dependency

**Files:**
- Modify: `frontend/package.json` (via pnpm)

- [ ] **Step 1: Install @monaco-editor/react**

Run: `cd frontend && pnpm add @monaco-editor/react`

- [ ] **Step 2: Verify installation**

Run: `cd frontend && node -e "require('@monaco-editor/react'); console.log('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat: add @monaco-editor/react dependency"
```

---

### Task 5: Frontend — TypeScript Types for File API

**Files:**
- Create: `frontend/src/types/file.ts`

- [ ] **Step 1: Create the types file**

```typescript
export interface FileContentResponse {
  content: string
  language: string
  exists: boolean
}

export interface FileDiffContentResponse {
  original: string
  modified: string
  language: string
}

export interface FileWriteRequest {
  project_id: string
  path: string
  content: string
}

export interface FileWriteResponse {
  success: boolean
  error: string | null
}
```

- [ ] **Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit src/types/file.ts`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/file.ts
git commit -m "feat: add TypeScript types for file content API"
```

---

### Task 6: Frontend — File API Client

**Files:**
- Create: `frontend/src/features/code/fileApi.ts`

- [ ] **Step 1: Create the API client file**

```typescript
import { apiClient } from '@/services/apiClient'
import type {
  FileContentResponse,
  FileDiffContentResponse,
  FileWriteRequest,
  FileWriteResponse,
} from '@/types/file'

export const fileApi = {
  getContent: (projectId: string, path: string) =>
    apiClient.get<FileContentResponse>('/api/files/content', {
      params: { project_id: projectId, path },
    }),

  getDiffContent: (projectId: string, path: string) =>
    apiClient.get<FileDiffContentResponse>('/api/files/diff-content', {
      params: { project_id: projectId, path },
    }),

  writeFile: (data: FileWriteRequest) =>
    apiClient.post<FileWriteResponse>('/api/files/write', data),
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit src/features/code/fileApi.ts`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/code/fileApi.ts
git commit -m "feat: add fileApi client for file content endpoints"
```

---

### Task 7: Frontend — Code Tab Zustand Store

**Files:**
- Create: `frontend/src/features/code/codeTabStore.ts`

- [ ] **Step 1: Create the store**

```typescript
import { create } from 'zustand'

export type WorkspaceTab = 'chat' | 'code'
export type CodeSubTab = 'diff' | 'edit'

export interface ActiveFile {
  path: string
  language: string
}

interface CodeTabState {
  workspaceTab: WorkspaceTab
  codeSubTab: CodeSubTab
  activeFile: ActiveFile | null
  isDirty: boolean
}

interface CodeTabActions {
  setWorkspaceTab: (tab: WorkspaceTab) => void
  setCodeSubTab: (subTab: CodeSubTab) => void
  setActiveFile: (path: string, language: string, defaultSubTab?: CodeSubTab) => void
  setDirty: (dirty: boolean) => void
  clearActiveFile: () => void
}

export const useCodeTabStore = create<CodeTabState & CodeTabActions>()((set) => ({
  workspaceTab: 'chat',
  codeSubTab: 'diff',
  activeFile: null,
  isDirty: false,

  setWorkspaceTab: (tab) => set({ workspaceTab: tab }),
  setCodeSubTab: (subTab) => set({ codeSubTab: subTab }),
  setActiveFile: (path, language, defaultSubTab) =>
    set((state) => ({
      activeFile: { path, language },
      isDirty: false,
      workspaceTab: 'code',
      codeSubTab: defaultSubTab ?? state.codeSubTab,
    })),
  setDirty: (dirty) => set({ isDirty: dirty }),
  clearActiveFile: () => set({ activeFile: null, isDirty: false }),
}))
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit src/features/code/codeTabStore.ts`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/code/codeTabStore.ts
git commit -m "feat: add codeTabStore for Code tab state management"
```

---

### Task 8: Frontend — CodeTabBar Component

**Files:**
- Create: `frontend/src/components/workspace/CodeTabBar.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { Save } from 'lucide-react'
import type { CodeSubTab } from '@/features/code/codeTabStore'

interface CodeTabBarProps {
  subTab: CodeSubTab
  onSubTabChange: (subTab: CodeSubTab) => void
  filename: string | null
  isDirty: boolean
  onSave: () => void
  showSave: boolean
}

export function CodeTabBar({
  subTab,
  onSubTabChange,
  filename,
  isDirty,
  onSave,
  showSave,
}: CodeTabBarProps) {
  const tabs: { key: CodeSubTab; label: string }[] = [
    { key: 'diff', label: 'Diff' },
    { key: 'edit', label: '编辑' },
  ]

  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2">
      <div className="flex items-center gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onSubTabChange(tab.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              subTab === tab.key
                ? 'bg-slate-100 text-slate-900'
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3">
        {filename && (
          <span className="text-sm text-slate-600">
            {isDirty && <span className="mr-1 text-amber-500">●</span>}
            {filename}
          </span>
        )}
        {showSave && (
          <button
            type="button"
            onClick={onSave}
            disabled={!isDirty}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Save className="h-3.5 w-3.5" />
            保存
          </button>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit src/components/workspace/CodeTabBar.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/CodeTabBar.tsx
git commit -m "feat: add CodeTabBar component with Diff/Edit sub-tabs"
```

---

### Task 9: Frontend — DiffViewer Component

**Files:**
- Create: `frontend/src/components/workspace/DiffViewer.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useRef, useEffect } from 'react'
import DiffEditor from '@monaco-editor/react'
import type { editor } from 'monaco-editor'

interface DiffViewerProps {
  original: string
  modified: string
  language: string
}

export function DiffViewer({ original, modified, language }: DiffViewerProps) {
  const editorRef = useRef<editor.IStandaloneDiffEditor | null>(null)

  function handleMount(editor: editor.IStandaloneDiffEditor) {
    editorRef.current = editor
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
        readOnly: true,
        renderSideBySide: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
      }}
    />
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit src/components/workspace/DiffViewer.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/DiffViewer.tsx
git commit -m "feat: add DiffViewer component with Monaco DiffEditor"
```

---

### Task 10: Frontend — CodeEditor Component

**Files:**
- Create: `frontend/src/components/workspace/CodeEditor.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useRef, useEffect, useCallback } from 'react'
import Editor from '@monaco-editor/react'
import type { editor } from 'monaco-editor'

interface CodeEditorProps {
  value: string
  language: string
  onChange: (value: string) => void
  onSave: () => void
}

export function CodeEditor({ value, language, onChange, onSave }: CodeEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)

  function handleMount(editorInstance: editor.IStandaloneCodeEditor) {
    editorRef.current = editorInstance
    editorInstance.addCommand(
      // KeyMod.CtrlCmd | KeyCode.KeyS
      2048 | 49,
      () => onSave(),
    )
  }

  useEffect(() => {
    if (editorRef.current) {
      const model = editorRef.current.getModel()
      if (model && model.getValue() !== value) {
        editorRef.current.setValue(value)
      }
    }
  }, [value])

  const handleChange = useCallback(
    (newValue: string | undefined) => {
      onChange(newValue ?? '')
    },
    [onChange],
  )

  return (
    <Editor
      height="100%"
      language={language}
      value={value}
      onChange={handleChange}
      onMount={handleMount}
      options={{
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
        wordWrap: 'on',
        tabSize: 2,
      }}
    />
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit src/components/workspace/CodeEditor.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/CodeEditor.tsx
git commit -m "feat: add CodeEditor component with Monaco Editor"
```

---

### Task 11: Frontend — CodeTab Container Component

**Files:**
- Create: `frontend/src/components/workspace/CodeTab.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useCallback, useEffect, useState } from 'react'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import { fileApi } from '@/features/code/fileApi'
import { CodeTabBar } from './CodeTabBar'
import { DiffViewer } from './DiffViewer'
import { CodeEditor } from './CodeEditor'
import { useProjectStore } from '@/stores/projectStore'

function CodeTabEmpty() {
  return (
    <div className="flex h-full items-center justify-center text-slate-400">
      点击聊天中的文件操作查看变更
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
  const codeSubTab = useCodeTabStore((s) => s.codeSubTab)
  const isDirty = useCodeTabStore((s) => s.isDirty)
  const setCodeSubTab = useCodeTabStore((s) => s.setCodeSubTab)
  const setDirty = useCodeTabStore((s) => s.setDirty)

  const currentProject = useProjectStore((s) => s.currentProject)
  const projectId = currentProject?.id ?? ''

  const [original, setOriginal] = useState('')
  const [modified, setModified] = useState('')
  const [editContent, setEditContent] = useState('')
  const [language, setLanguage] = useState('plaintext')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!activeFile || !projectId) return

    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        if (codeSubTab === 'diff') {
          const resp = await fileApi.getDiffContent(projectId, activeFile.path)
          if (cancelled) return
          const data = resp.data
          setOriginal(data.original)
          setModified(data.modified)
          setLanguage(data.language)
          setEditContent(data.modified)
        } else {
          const resp = await fileApi.getContent(projectId, activeFile.path)
          if (cancelled) return
          const data = resp.data
          setEditContent(data.content)
          setLanguage(data.language)
        }
      } catch (err) {
        if (cancelled) return
        console.error('Failed to load file:', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [activeFile, projectId, codeSubTab])

  const handleEditChange = useCallback(
    (newValue: string) => {
      setEditContent(newValue)
      setDirty(true)
    },
    [setDirty],
  )

  const handleSave = useCallback(async () => {
    if (!activeFile || !projectId) return
    try {
      const resp = await fileApi.writeFile({
        project_id: projectId,
        path: activeFile.path,
        content: editContent,
      })
      if (resp.data.success) {
        setDirty(false)
      } else {
        console.error('Save failed:', resp.data.error)
      }
    } catch (err) {
      console.error('Save failed:', err)
    }
  }, [activeFile, projectId, editContent, setDirty])

  if (!activeFile) {
    return <CodeTabEmpty />
  }

  const filename = activeFile.path.split('/').pop() ?? activeFile.path

  return (
    <div className="flex h-full flex-col">
      <CodeTabBar
        subTab={codeSubTab}
        onSubTabChange={setCodeSubTab}
        filename={filename}
        isDirty={isDirty}
        onSave={handleSave}
        showSave={codeSubTab === 'edit'}
      />
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <CodeTabLoading />
        ) : codeSubTab === 'diff' ? (
          <DiffViewer original={original} modified={modified} language={language} />
        ) : (
          <CodeEditor
            value={editContent}
            language={language}
            onChange={handleEditChange}
            onSave={handleSave}
          />
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit src/components/workspace/CodeTab.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/workspace/CodeTab.tsx
git commit -m "feat: add CodeTab container with diff/edit switching"
```

---

### Task 12: Frontend — Make Receipt Rows Clickable

**Files:**
- Modify: `frontend/src/components/execution/ActionReceipt.tsx`
- Modify: `frontend/src/components/execution/receiptUtils.ts`

- [ ] **Step 1: Add receipt click callback to ActionReceiptDetailRow**

In `frontend/src/components/execution/ActionReceipt.tsx`, modify the `ActionReceiptDetailRow` component.

Add a new optional prop to the interface (inside the component function, before the return):

Change the component signature from:
```typescript
function ActionReceiptDetailRow({ detail }: { detail: ActionReceiptDetail }) {
```
to:
```typescript
function ActionReceiptDetailRow({
  detail,
  onDetailClick,
}: {
  detail: ActionReceiptDetail
  onDetailClick?: (detail: ActionReceiptDetail) => void
}) {
```

Add `isClickable` logic after the state declarations:
```typescript
  const isClickable = onDetailClick != null
    && (detail.category === 'edit' || detail.category === 'create' || detail.category === 'delete')
```

Modify the outermost `<div>` in the return to add click handler and cursor styles. Change:
```typescript
    <div>
      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
```
to:
```typescript
    <div
      className={isClickable ? 'cursor-pointer' : ''}
      onClick={isClickable ? () => onDetailClick!(detail) : undefined}
    >
      <div className={`flex flex-wrap items-center gap-2 text-sm ${isClickable ? 'rounded-md px-1 py-0.5 -mx-1 -my-0.5 hover:bg-slate-50 transition-colors' : 'text-slate-600'}`}>
```

- [ ] **Step 2: Add onDetailClick prop threading to ActionReceipt**

In the same file, add `onDetailClick` to `ActionReceiptProps`:
```typescript
interface ActionReceiptProps {
  status: ActionReceiptStatus
  details: ActionReceiptDetail[]
  onApprovalAction?: (action: ApprovalActionType, payload: ApprovalActionPayload) => void
  onDetailClick?: (detail: ActionReceiptDetail) => void
}
```

Update the component function signature:
```typescript
export function ActionReceipt({ status, details, onApprovalAction, onDetailClick }: ActionReceiptProps) {
```

Pass `onDetailClick` to the row:
Change:
```typescript
                <ActionReceiptDetailRow key={detail.id} detail={detail} />
```
to:
```typescript
                <ActionReceiptDetailRow key={detail.id} detail={detail} onDetailClick={onDetailClick} />
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/execution/ActionReceipt.tsx
git commit -m "feat: make edit/create/delete receipt rows clickable"
```

---

### Task 13: Frontend — Thread onDetailClick Through ToolTraceCard and WorkspaceTranscript

**Files:**
- Modify: `frontend/src/components/workspace/ToolTraceCard.tsx`
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`

- [ ] **Step 1: Update ToolTraceGroup to accept and pass onDetailClick**

In `frontend/src/components/workspace/ToolTraceCard.tsx`, update `ToolTraceGroup`:

Change:
```typescript
export function ToolTraceGroup({
  details,
  status,
  onApprovalAction,
}: {
  details: ActionReceiptDetail[]
  status: ActionReceiptStatus
  onApprovalAction?: ToolApprovalActionHandler
}) {
  return (
    <ActionReceipt
      status={status}
      details={details}
      onApprovalAction={onApprovalAction}
    />
  )
}
```
to:
```typescript
export type ReceiptDetailClickHandler = (detail: ActionReceiptDetail) => void

export function ToolTraceGroup({
  details,
  status,
  onApprovalAction,
  onDetailClick,
}: {
  details: ActionReceiptDetail[]
  status: ActionReceiptStatus
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: ReceiptDetailClickHandler
}) {
  return (
    <ActionReceipt
      status={status}
      details={details}
      onApprovalAction={onApprovalAction}
      onDetailClick={onDetailClick}
    />
  )
}
```

- [ ] **Step 2: Add onDetailClick prop to WorkspaceTranscript**

In `frontend/src/components/workspace/WorkspaceTranscript.tsx`:

Add import for `ActionReceiptDetail`:
```typescript
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
```

Add `onDetailClick` to `WorkspaceTranscriptProps`:
```typescript
  onApprovalAction?: ToolApprovalActionHandler
  onDetailClick?: (detail: ActionReceiptDetail) => void
  messagesEndRef: RefObject<HTMLDivElement>
```

Add to destructured props:
```typescript
  onApprovalAction,
  onDetailClick,
  messagesEndRef,
```

Pass to `ToolTraceGroup`:
```typescript
                  <ToolTraceGroup
                    status={item.status}
                    details={item.details}
                    onApprovalAction={onApprovalAction}
                    onDetailClick={onDetailClick}
                  />
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/workspace/ToolTraceCard.tsx frontend/src/components/workspace/WorkspaceTranscript.tsx
git commit -m "feat: thread onDetailClick through ToolTraceGroup and WorkspaceTranscript"
```

---

### Task 14: Frontend — Integrate Chat/Code Tab Bar and Code Tab into AgentWorkspace

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceHeader.tsx`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **Step 1: Add workspace tab switcher to WorkspaceHeader**

In `frontend/src/components/workspace/WorkspaceHeader.tsx`, add the Chat/Code tab switcher.

Add import:
```typescript
import { useCodeTabStore, type WorkspaceTab } from '@/features/code/codeTabStore'
```

Add `workspaceTab` and `setWorkspaceTab` from store inside the component:
```typescript
  const workspaceTab = useCodeTabStore((s) => s.workspaceTab)
  const setWorkspaceTab = useCodeTabStore((s) => s.setWorkspaceTab)
```

Add tab buttons to the header. Between the title div and the right-side status div, insert:

```typescript
        <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1">
          {(['chat', 'code'] as WorkspaceTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setWorkspaceTab(tab)}
              className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                workspaceTab === tab
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab === 'chat' ? '对话' : '代码'}
            </button>
          ))}
        </div>
```

- [ ] **Step 2: Modify AgentWorkspace to show CodeTab when Code tab is active**

In `frontend/src/pages/AgentWorkspace.tsx`:

Add imports:
```typescript
import { CodeTab } from '@/components/workspace/CodeTab'
import { useCodeTabStore } from '@/features/code/codeTabStore'
import type { ActionReceiptDetail } from '@/components/execution/receiptUtils'
```

Inside `AgentWorkspace`, add store selectors and click handler:
```typescript
  const workspaceTab = useCodeTabStore((s) => s.workspaceTab)
  const setActiveFile = useCodeTabStore((s) => s.setActiveFile)

  const handleDetailClick = useCallback((detail: ActionReceiptDetail) => {
    const path = detail.arguments?.path as string | undefined
    if (!path) return
    const defaultSubTab = detail.category === 'edit' || detail.category === 'create' ? 'diff' : 'edit'
    setActiveFile(path, '', defaultSubTab)
  }, [setActiveFile])
```

Add `useCallback` to the existing imports from react.

Modify the render to conditionally show CodeTab or chat:

Replace the content inside the main return `<div className="flex h-full flex-col bg-white">` with:

```typescript
      <div className="flex h-full flex-col bg-white">
        <WorkspaceHeader {...viewModel.headerProps} />

        {workspaceTab === 'code' ? (
          <CodeTab />
        ) : (
          <>
            <WorkspaceTranscript
              {...viewModel.transcriptProps}
              runsById={runsById}
              isPlanMinimized={effectivePlanMinimized}
              onTogglePlanMinimize={() => setIsPlanMinimized((v) => !v)}
              onDetailClick={handleDetailClick}
            />

            <div className="border-t border-gray-200 bg-white">
              {plan && effectivePlanMinimized && (
                <PlanMinimizedBar
                  plan={plan}
                  onExpand={() => setIsPlanMinimized(false)}
                />
              )}
              <div className="p-4">
                <ChatInput
                  onSend={sendMessage}
                  onCancel={cancelRun}
                  {...viewModel.inputProps}
                />
                {!viewModel.currentProject && (
                  <p className="mt-2 text-sm text-gray-500">请先从左侧选择一个项目</p>
                )}
              </div>
            </div>
          </>
        )}
      </div>
```

- [ ] **Step 3: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Run the frontend tests**

Run: `cd frontend && pnpm test`
Expected: All existing tests pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/workspace/WorkspaceHeader.tsx frontend/src/pages/AgentWorkspace.tsx
git commit -m "feat: integrate Chat/Code tab switching and receipt click handler"
```

---

### Task 15: Backend — Run All Tests

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: All tests pass (95+ existing + 7 new file content tests)

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && pnpm test`
Expected: All tests pass

- [ ] **Step 3: Run frontend linter**

Run: `cd frontend && pnpm lint`
Expected: No errors

---

### Task 16: Manual Smoke Test

- [ ] **Step 1: Start the dev server**

Run: `cd frontend && pnpm dev`

- [ ] **Step 2: Verify Chat/Code tab switcher appears**

Open the app, select a project and session. Verify:
- "对话" / "代码" tab switcher appears in the header
- Default tab is "对话" showing the chat

- [ ] **Step 3: Verify Code tab empty state**

Click "代码" tab. Verify:
- Empty state message appears: "点击聊天中的文件操作查看变更"
- Switching back to "对话" works

- [ ] **Step 4: Verify receipt click opens Code tab**

In the chat, find a receipt for a file edit/create/delete operation. Click it. Verify:
- Automatically switches to "代码" tab
- Diff view shows the file changes (original vs modified)
- File name appears in the sub-tab bar

- [ ] **Step 5: Verify Diff/Edit sub-tab switching**

In the Code tab, verify:
- Clicking "编辑" switches to the editable Monaco editor
- Clicking "Diff" switches back to the diff view
- Content is consistent between views

- [ ] **Step 6: Verify edit and save**

In Edit mode:
- Make a change to the file
- Dirty indicator (●) appears next to filename
- Click "保存" or Ctrl+S
- Dirty indicator disappears
- Verify file on disk was actually updated

- [ ] **Step 7: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address smoke test issues"
```
