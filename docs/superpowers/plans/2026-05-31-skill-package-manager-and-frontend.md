# Skill Package Manager & Frontend Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Git-based skill installation/uninstallation, show skill source/origin metadata, enable clicking a skill to open its SKILL.md in the Monaco code editor, and add install/uninstall UI controls.

**Architecture:** Backend `SkillInstaller` clones Git repos into `~/.reflexion/skills/` (or project `skills/`), `SkillMetadata` gains `source`/`install_path` fields, new API endpoints for install/uninstall/refresh, frontend SkillsPage adds install dialog and "open in editor" button that uses `codeTabStore.openFile()`.

**Tech Stack:** Python (FastAPI, Pydantic, gitpython), TypeScript (React, Monaco Editor, zustand)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/orchestration/skill_installer.py` | NEW — Git clone, install, uninstall logic |
| `backend/app/orchestration/skill_registry.py` | Modify — add `source`/`install_path` fields, refresh method |
| `backend/app/orchestration/skill_parser.py` | Modify — parse `source` from frontmatter |
| `backend/app/api/routes/skills.py` | Modify — add install/uninstall/refresh endpoints |
| `backend/app/tools/skill_tool.py` | Modify — add `install`/`uninstall` actions for agent |
| `backend/app/config/settings.py` | Modify — add install_dir to SkillSettings |
| `frontend/src/types/skill.ts` | Modify — add source/install_path fields |
| `frontend/src/features/skills/skillApi.ts` | Modify — add install/uninstall/refresh API calls |
| `frontend/src/pages/SkillsPage.tsx` | Modify — add install dialog, open-in-editor button, source badges, refresh |

---

### Task 1: SkillMetadata Source & Install Path Fields

**Files:**
- Modify: `backend/app/orchestration/skill_parser.py`
- Modify: `backend/app/orchestration/skill_registry.py`
- Modify: `backend/tests/test_orchestration/test_skill_parser.py`
- Modify: `backend/tests/test_orchestration/test_skill_registry.py`

- [ ] **Step 1: Add `source` and `install_path` to SkillFrontmatter**

In `backend/app/orchestration/skill_parser.py`, add to `SkillFrontmatter`:

```python
class SkillFrontmatter(BaseModel):
    name: str
    description: str
    category: str = ""
    required_skills: list[str] = []
    source: str = ""
```

In `parse_skill_md`, add `source=data.get("source", "")` to the frontmatter construction.

- [ ] **Step 2: Add `source` and `install_path` to SkillMetadata**

In `backend/app/orchestration/skill_registry.py`:

```python
class SkillMetadata(BaseModel):
    name: str
    description: str
    category: str = ""
    required_skills: list[str] = []
    file_path: str = ""
    enabled: bool = True
    content_loaded: bool = False
    source: str = ""
    install_path: str = ""
```

In `scan_directory`, set `source=fm.source` and `install_path=str(child)` (the directory containing the SKILL.md).

- [ ] **Step 3: Update tests**

Add test for `source` field parsing in `test_skill_parser.py` and for `source`/`install_path` in `test_skill_registry.py`.

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_parser.py tests/test_orchestration/test_skill_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestration/skill_parser.py backend/app/orchestration/skill_registry.py backend/tests/test_orchestration/test_skill_parser.py backend/tests/test_orchestration/test_skill_registry.py
git commit -m "feat: add source and install_path fields to SkillMetadata"
```

---

### Task 2: SkillInstaller — Git-Based Install/Uninstall

**Files:**
- Create: `backend/app/orchestration/skill_installer.py`
- Create: `backend/tests/test_orchestration/test_skill_installer.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.orchestration.skill_installer import SkillInstaller, InstallResult


class TestSkillInstaller:
    def test_install_from_git_url(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)

        with patch("app.orchestration.skill_installer.Repo") as mock_repo:
            mock_repo.clone_from.return_value = MagicMock()

            result = installer.install(
                url="https://github.com/example/skills.git",
                skill_name="brainstorming",
            )

        assert result.success
        mock_repo.clone_from.assert_called_once()
        assert result.install_path == str(tmp_path / "brainstorming")

    def test_install_skill_already_exists(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)
        skill_dir = tmp_path / "brainstorming"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: brainstorming\ndescription: test\n---\n\n# Test\n',
            encoding="utf-8",
        )

        result = installer.install(
            url="https://github.com/example/skills.git",
            skill_name="brainstorming",
        )

        assert result.success is False
        assert "already exists" in result.error

    def test_uninstall_skill(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: my-skill\ndescription: test\n---\n\n# Test\n',
            encoding="utf-8",
        )

        result = installer.uninstall("my-skill")

        assert result.success
        assert not skill_dir.exists()

    def test_uninstall_nonexistent_skill(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)

        result = installer.uninstall("nonexistent")

        assert result.success is False
        assert "not found" in result.error

    def test_install_with_subdir(self, tmp_path):
        installer = SkillInstaller(install_dir=tmp_path)

        with patch("app.orchestration.skill_installer.Repo") as mock_repo:
            mock_repo_obj = MagicMock()
            mock_repo.clone_from.return_value = mock_repo_obj

            # Simulate sparse checkout: the installer clones the repo,
            # then copies the subdirectory
            result = installer.install(
                url="https://github.com/example/skills.git",
                skill_name="brainstorming",
                subdir="skills/brainstorming",
            )

        assert result.success

    def test_install_result_model(self):
        r = InstallResult(success=True, install_path="/some/path")
        assert r.success
        assert r.install_path == "/some/path"

        r2 = InstallResult(success=False, error="fail")
        assert r2.success is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_installer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
import logging
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class InstallResult(BaseModel):
    success: bool
    install_path: str = ""
    error: str = ""


class SkillInstaller:
    def __init__(self, install_dir: Path | str):
        self.install_dir = Path(install_dir)
        self.install_dir.mkdir(parents=True, exist_ok=True)

    def install(
        self,
        url: str,
        skill_name: str,
        subdir: str = "",
        branch: str = "main",
    ) -> InstallResult:
        target_dir = self.install_dir / skill_name
        if target_dir.exists():
            return InstallResult(
                success=False,
                error=f"Skill '{skill_name}' already exists at {target_dir}",
            )

        try:
            from git import Repo

            with TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                clone_dir = tmp_path / "repo"
                logger.info("Cloning %s (branch=%s) to %s", url, branch, clone_dir)
                Repo.clone_from(url, str(clone_dir), branch=branch, depth=1)

                source_dir = clone_dir / subdir if subdir else clone_dir / skill_name
                if not source_dir.is_dir():
                    source_dir = clone_dir
                    if not (source_dir / "SKILL.md").exists():
                        return InstallResult(
                            success=False,
                            error=f"SKILL.md not found in repo at {subdir or skill_name}",
                        )

                skill_file = source_dir / "SKILL.md"
                if not skill_file.exists():
                    return InstallResult(
                        success=False,
                        error=f"SKILL.md not found at {source_dir}",
                    )

                shutil.copytree(str(source_dir), str(target_dir))
                logger.info("Installed skill '%s' to %s", skill_name, target_dir)

            return InstallResult(
                success=True,
                install_path=str(target_dir),
            )
        except Exception as exc:
            logger.exception("Failed to install skill '%s'", skill_name)
            return InstallResult(success=False, error=str(exc))

    def uninstall(self, skill_name: str) -> InstallResult:
        target_dir = self.install_dir / skill_name
        if not target_dir.exists():
            return InstallResult(
                success=False,
                error=f"Skill '{skill_name}' not found at {target_dir}",
            )

        try:
            shutil.rmtree(str(target_dir))
            logger.info("Uninstalled skill '%s'", skill_name)
            return InstallResult(success=True, install_path=str(target_dir))
        except Exception as exc:
            logger.exception("Failed to uninstall skill '%s'", skill_name)
            return InstallResult(success=False, error=str(exc))
```

- [ ] **Step 4: Verify gitpython is installed**

Run: `cd backend && python -c "from git import Repo; print('gitpython OK')"`
If not installed: `pip install gitpython`

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_installer.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/orchestration/skill_installer.py backend/tests/test_orchestration/test_skill_installer.py
git commit -m "feat: add SkillInstaller with Git-based install/uninstall"
```

---

### Task 3: Wire Installer into SkillSettings, Registry, and API

**Files:**
- Modify: `backend/app/config/settings.py` — add `install_dir` to SkillSettings
- Modify: `backend/app/orchestration/skill_registry.py` — add `refresh()` and `install_skill()`/`uninstall_skill()` methods
- Modify: `backend/app/api/routes/skills.py` — add install/uninstall/refresh endpoints
- Create: `backend/tests/test_api/test_skills_api_install.py`

- [ ] **Step 1: Add install_dir to SkillSettings**

In `backend/app/config/settings.py`:

```python
class SkillSettings(BaseModel):
    scan_dirs: list[str] = Field(default_factory=list)
    auto_scan: bool = True
    install_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".reflexion" / "skills")
    )
```

- [ ] **Step 2: Add registry methods**

In `backend/app/orchestration/skill_registry.py`, add:

```python
from app.orchestration.skill_installer import SkillInstaller, InstallResult

class SkillRegistry:
    def __init__(self):
        self.skills: dict[str, SkillMetadata] = {}
        self._content_cache: dict[str, str] = {}
        self._installer: SkillInstaller | None = None

    def get_installer(self) -> SkillInstaller:
        if self._installer is None:
            from app.config.settings import config_manager
            install_dir = config_manager.settings.skill.install_dir
            self._installer = SkillInstaller(install_dir)
        return self._installer

    def install_skill(self, url: str, skill_name: str, subdir: str = "", branch: str = "main") -> InstallResult:
        result = self.get_installer().install(url, skill_name, subdir, branch)
        if result.success:
            self.scan_directory(result.install_path)
        return result

    def uninstall_skill(self, name: str) -> InstallResult:
        skill = self.get_skill(name)
        if skill is None:
            return InstallResult(success=False, error=f"Skill '{name}' not registered")
        result = self.get_installer().uninstall(name)
        if result.success:
            self.unregister_skill(name)
        return result

    def refresh(self) -> int:
        self.skills.clear()
        self._content_cache.clear()
        from app.config.settings import config_manager
        skill_settings = config_manager.settings.skill
        total = 0
        project_skills = Path.cwd() / "skills"
        if project_skills.exists():
            total += self.scan_directory(project_skills)
        global_skills = Path(skill_settings.install_dir)
        if global_skills.exists():
            total += self.scan_directory(global_skills)
        for extra_dir in skill_settings.scan_dirs:
            p = Path(extra_dir)
            if p.exists():
                total += self.scan_directory(p)
        return total
```

- [ ] **Step 3: Add API endpoints**

In `backend/app/api/routes/skills.py`, add:

```python
from pydantic import BaseModel


class InstallRequest(BaseModel):
    url: str
    skill_name: str
    subdir: str = ""
    branch: str = "main"


@router.post("/install")
async def install_skill(req: InstallRequest):
    result = skill_registry.install_skill(
        url=req.url,
        skill_name=req.skill_name,
        subdir=req.subdir,
        branch=req.branch,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    skill = skill_registry.get_skill(req.skill_name)
    return {
        "name": skill.name if skill else req.skill_name,
        "install_path": result.install_path,
        "installed": True,
    }


@router.delete("/{skill_name}")
async def uninstall_skill(skill_name: str):
    result = skill_registry.uninstall_skill(skill_name)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"name": skill_name, "uninstalled": True}


@router.post("/refresh")
async def refresh_skills():
    count = skill_registry.refresh()
    return {"total_skills": count}
```

Also update `list_skills` to include `source` and `install_path` in the response dict.

- [ ] **Step 4: Write API test**

Create `backend/tests/test_api/test_skills_api_install.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.orchestration.skill_registry import SkillMetadata, skill_registry
from app.orchestration.skill_installer import InstallResult


@pytest.fixture(autouse=True)
def _reset_registry():
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()
    skill_registry._installer = None
    yield
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()
    skill_registry._installer = None


client = TestClient(app)


class TestSkillsInstallAPI:
    def test_install_skill(self):
        with patch.object(skill_registry, "install_skill") as mock_install:
            mock_install.return_value = InstallResult(
                success=True, install_path="/tmp/skills/brainstorming"
            )
            skill_registry.register_skill(
                SkillMetadata(
                    name="brainstorming",
                    description="test",
                    install_path="/tmp/skills/brainstorming",
                )
            )
            resp = client.post("/api/skills/install", json={
                "url": "https://github.com/example/skills.git",
                "skill_name": "brainstorming",
            })
        assert resp.status_code == 200
        assert resp.json()["installed"] is True

    def test_install_skill_fails(self):
        with patch.object(skill_registry, "install_skill") as mock_install:
            mock_install.return_value = InstallResult(
                success=False, error="already exists"
            )
            resp = client.post("/api/skills/install", json={
                "url": "https://github.com/example/skills.git",
                "skill_name": "brainstorming",
            })
        assert resp.status_code == 400

    def test_uninstall_skill(self):
        skill_registry.register_skill(
            SkillMetadata(name="test-skill", description="test", install_path="/tmp/skills/test-skill")
        )
        with patch.object(skill_registry, "uninstall_skill") as mock_uninstall:
            mock_uninstall.return_value = InstallResult(success=True)
            resp = client.delete("/api/skills/test-skill")
        assert resp.status_code == 200
        assert resp.json()["uninstalled"] is True

    def test_uninstall_nonexistent(self):
        with patch.object(skill_registry, "uninstall_skill") as mock_uninstall:
            mock_uninstall.return_value = InstallResult(success=False, error="not found")
            resp = client.delete("/api/skills/nonexistent")
        assert resp.status_code == 400

    def test_refresh_skills(self):
        with patch.object(skill_registry, "refresh", return_value=5):
            resp = client.post("/api/skills/refresh")
        assert resp.status_code == 200
        assert resp.json()["total_skills"] == 5
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_api/test_skills_api_install.py tests/test_api/test_skills_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/config/settings.py backend/app/orchestration/skill_registry.py backend/app/api/routes/skills.py backend/tests/test_api/test_skills_api_install.py
git commit -m "feat: wire SkillInstaller into registry and API with install/uninstall/refresh endpoints"
```

---

### Task 4: Add Install/Uninstall to SkillTool (Agent)

**Files:**
- Modify: `backend/app/tools/skill_tool.py`
- Modify: `backend/tests/test_tools/test_skill_tool.py`

- [ ] **Step 1: Add `install` and `uninstall` actions to SkillTool schema**

In `skill_tool.py`, update `get_schema` to add:

```python
"action": {
    "type": "string",
    "enum": ["list", "load", "search", "install", "uninstall"],
    "description": ("Action: 'list' all skills, 'load' a skill's "
                    "content, 'search' by keyword, 'install' from "
                    "a Git URL, 'uninstall' a skill"),
},
"url": {
    "type": "string",
    "description": "Git repository URL (required for 'install')",
},
"skill_name": {
    "type": "string",
    "description": "Skill name (required for 'install' and 'uninstall')",
},
"subdir": {
    "type": "string",
    "description": "Subdirectory path within repo (optional for 'install')",
},
```

Change `"name"` param to `"skill_name"` (keep backward compat by reading both in execute).

- [ ] **Step 2: Add install/uninstall handlers in execute**

```python
if action == "install":
    url = args.get("url", "")
    s_name = args.get("skill_name") or args.get("name", "")
    if not url or not s_name:
        return ToolResult(success=False, error="url and skill_name required for install")
    subdir = args.get("subdir", "")
    result = self._registry.install_skill(url, s_name, subdir)
    if result.success:
        return ToolResult(success=True, output=f"Installed skill '{s_name}' to {result.install_path}")
    return ToolResult(success=False, error=result.error)

if action == "uninstall":
    s_name = args.get("skill_name") or args.get("name", "")
    if not s_name:
        return ToolResult(success=False, error="skill_name required for uninstall")
    result = self._registry.uninstall_skill(s_name)
    if result.success:
        return ToolResult(success=True, output=f"Uninstalled skill '{s_name}'")
    return ToolResult(success=False, error=result.error)
```

- [ ] **Step 3: Add tests**

```python
def test_execute_install(self, registry):
    tool = SkillTool(registry)
    with patch.object(registry, "install_skill") as mock:
        mock.return_value = InstallResult(success=True, install_path="/tmp/new-skill")
        result = tool.execute({"action": "install", "url": "https://github.com/x/skills.git", "skill_name": "new-skill"})
    assert result.success
    assert "Installed" in result.output

def test_execute_uninstall(self, registry):
    tool = SkillTool(registry)
    with patch.object(registry, "uninstall_skill") as mock:
        mock.return_value = InstallResult(success=True)
        result = tool.execute({"action": "uninstall", "skill_name": "brainstorming"})
    assert result.success
    assert "Uninstalled" in result.output
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_tools/test_skill_tool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/skill_tool.py backend/tests/test_tools/test_skill_tool.py
git commit -m "feat: add install/uninstall actions to SkillTool for agent"
```

---

### Task 5: Frontend — Update Types, API, and Source Display

**Files:**
- Modify: `frontend/src/types/skill.ts`
- Modify: `frontend/src/features/skills/skillApi.ts`
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: Update types**

In `frontend/src/types/skill.ts`:

```typescript
export interface Skill {
  name: string
  description: string
  category: string
  required_skills: string[]
  enabled: boolean
  source: string
  install_path: string
}

export interface SkillDetail extends Skill {
  content: string
}

export interface SkillCategories {
  [category: string]: { name: string; description: string; enabled: boolean }[]
}

export interface InstallRequest {
  url: string
  skill_name: string
  subdir?: string
  branch?: string
}
```

- [ ] **Step 2: Update API**

In `frontend/src/features/skills/skillApi.ts`:

```typescript
import { apiClient } from '@/services/apiClient'
import type { Skill, SkillDetail, SkillCategories, InstallRequest } from '@/types/skill'

export const skillApi = {
  list: () => apiClient.get<Skill[]>('/api/skills'),
  detail: (name: string) => apiClient.get<SkillDetail>(`/api/skills/${name}`),
  categories: () => apiClient.get<SkillCategories>('/api/skills/categories'),
  enable: (name: string) => apiClient.post(`/api/skills/${name}/enable`),
  disable: (name: string) => apiClient.post(`/api/skills/${name}/disable`),
  install: (req: InstallRequest) => apiClient.post('/api/skills/install', req),
  uninstall: (name: string) => apiClient.delete(`/api/skills/${name}`),
  refresh: () => apiClient.post('/api/skills/refresh'),
}
```

- [ ] **Step 3: Update SkillsPage — add source badge, install dialog, open-in-editor button, refresh, uninstall**

Key changes to `frontend/src/pages/SkillsPage.tsx`:

1. **Source badge**: On each skill card, show where the skill comes from:
   - If `source` is set → show git URL badge
   - If `install_path` starts with `~/.reflexion/skills` → "全局安装" badge
   - If `install_path` is under project `skills/` → "项目内置" badge
   - Otherwise → "本地" badge

2. **Open in editor button**: Each skill card gets a "在编辑器中查看" button. On click:
   ```typescript
   import { useCodeTabStore } from '@/features/code/codeTabStore'
   const openFile = useCodeTabStore((s) => s.openFile)
   // skill.file_path is the SKILL.md path relative to project
   openFile(skill.install_path + '/SKILL.md', 'edit')
   ```
   This switches to the Code tab and opens SKILL.md in Monaco.

3. **Install dialog**: A "+" button that opens a dialog with:
   - URL input (Git repository URL)
   - Skill name input
   - Optional subdir input
   - Install button → calls `skillApi.install(...)`

4. **Uninstall button**: On each installed skill card, a trash icon that calls `skillApi.uninstall(name)` and refreshes the list.

5. **Refresh button**: A refresh icon in the header that calls `skillApi.refresh()` and reloads the list.

6. **Empty state fix**: If skills list is empty after loading, show a helpful message encouraging to install skills.

- [ ] **Step 4: Verify TypeScript and build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/skill.ts frontend/src/features/skills/skillApi.ts frontend/src/pages/SkillsPage.tsx
git commit -m "feat: frontend skill source display, install dialog, open-in-editor, uninstall"
```

---

### Task 6: Integration Test & Cleanup

**Files:**
- Various

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run full frontend build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Run backend lint**

Run: `cd backend && python -m ruff check app/ tests/`
Expected: No errors (fix any that appear)

- [ ] **Step 4: Verify install flow end-to-end**

Run: `cd backend && python -c "
from app.orchestration.skill_installer import SkillInstaller
from app.orchestration.skill_registry import SkillRegistry
r = SkillRegistry()
r.scan_directory('../skills')
print(f'Before: {len(r.list_skills())} skills')
print('Install/uninstall mechanism ready')
"`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: integration test and cleanup for skill package manager"
```
