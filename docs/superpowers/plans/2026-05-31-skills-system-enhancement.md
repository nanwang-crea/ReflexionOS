# Skills System Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance ReflexionOS's skill system to match opencode's SKILL.md-based design: file-system-driven discovery, YAML frontmatter metadata, lazy content loading, CSO-optimized descriptions, skill type classification, and runtime prompt injection.

**Architecture:** Extend `SkillRegistry` to scan `skills/` directories (project-local + `~/.reflexion/skills/`), parse SKILL.md files with YAML frontmatter, expose list (metadata-only) and detail (full-content) endpoints, and inject enabled skill content into the LLM system prompt via `ContextAssembler`.

**Tech Stack:** Python (FastAPI, Pydantic, PyYAML), TypeScript (React, Vite)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/orchestration/skill_registry.py` | Core registry: scan, parse, register, lazy-load SKILL.md |
| `backend/app/orchestration/skill_parser.py` | NEW — Parse SKILL.md: YAML frontmatter + markdown body |
| `backend/app/api/routes/skills.py` | REST API: list (metadata), detail (content), enable/disable |
| `backend/app/config/settings.py` | Add `SkillSettings` with scan_dirs config |
| `backend/app/memory/context_assembly.py` | Inject enabled skill content into system sections |
| `backend/app/tools/skill_tool.py` | NEW — LLM-callable tool: agent can load a skill on demand |
| `frontend/src/types/skill.ts` | Extended Skill type with category, content_path, etc. |
| `frontend/src/features/skills/skillApi.ts` | Add detail, enable, disable API calls |
| `frontend/src/pages/SkillsPage.tsx` | Redesigned: category tabs, detail drawer, enable/disable toggle |

---

### Task 1: SKILL.md Parser

**Files:**
- Create: `backend/app/orchestration/skill_parser.py`
- Test: `backend/tests/test_orchestration/test_skill_parser.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.orchestration.skill_parser import parse_skill_md, SkillFrontmatter


class TestSkillParser:
    def test_parse_basic_skill(self, tmp_path):
        skill_file = tmp_path / "brainstorming" / "SKILL.md"
        skill_file.parent.mkdir()
        skill_file.write_text(
            '---\n'
            'name: brainstorming\n'
            'description: "Use when you need to explore ideas before implementation."\n'
            '---\n'
            '\n'
            '# Brainstorming\n'
            '\n'
            '## Overview\n'
            '\n'
            'Help turn ideas into designs.\n',
            encoding="utf-8",
        )

        result = parse_skill_md(skill_file)

        assert result.frontmatter.name == "brainstorming"
        assert "Use when" in result.frontmatter.description
        assert "Help turn ideas into designs" in result.body

    def test_parse_skill_without_frontmatter(self, tmp_path):
        skill_file = tmp_path / "no-fm" / "SKILL.md"
        skill_file.parent.mkdir()
        skill_file.write_text("# Plain Skill\n\nNo frontmatter here.\n", encoding="utf-8")

        result = parse_skill_md(skill_file)

        assert result.frontmatter.name == "no-fm"
        assert result.frontmatter.description == ""
        assert "Plain Skill" in result.body

    def test_parse_skill_with_category(self, tmp_path):
        skill_file = tmp_path / "tdd" / "SKILL.md"
        skill_file.parent.mkdir()
        skill_file.write_text(
            '---\n'
            'name: test-driven-development\n'
            'description: "Use when implementing any feature or bugfix."\n'
            'category: discipline\n'
            '---\n'
            '\n'
            '# TDD\n',
            encoding="utf-8",
        )

        result = parse_skill_md(skill_file)

        assert result.frontmatter.category == "discipline"

    def test_parse_skill_with_required_subskills(self, tmp_path):
        skill_file = tmp_path / "discipline" / "SKILL.md"
        skill_file.parent.mkdir()
        skill_file.write_text(
            '---\n'
            'name: code-implementation-discipline\n'
            'description: "Use when scope pressure exists."\n'
            'required_skills:\n'
            '  - brainstorming\n'
            '  - systematic-debugging\n'
            '---\n'
            '\n'
            '# Discipline\n',
            encoding="utf-8",
        )

        result = parse_skill_md(skill_file)

        assert result.frontmatter.required_skills == ["brainstorming", "systematic-debugging"]

    def test_parse_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            parse_skill_md("/nonexistent/SKILL.md")

    def test_parse_empty_frontmatter(self, tmp_path):
        skill_file = tmp_path / "empty-fm" / "SKILL.md"
        skill_file.parent.mkdir()
        skill_file.write_text("---\n---\n\n# Empty FM\n", encoding="utf-8")

        result = parse_skill_md(skill_file)

        assert result.frontmatter.name == "empty-fm"
        assert result.body == "# Empty FM\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.orchestration.skill_parser'`

- [ ] **Step 3: Write minimal implementation**

```python
import logging
import re
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SkillFrontmatter(BaseModel):
    name: str = ""
    description: str = ""
    category: str = ""
    required_skills: list[str] = []


class ParsedSkill(BaseModel):
    frontmatter: SkillFrontmatter
    body: str
    file_path: str


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_skill_md(path: Path | str) -> ParsedSkill:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    fm_match = _FRONTMATTER_RE.match(raw)
    directory_name = path.parent.name

    if fm_match:
        yaml_text = fm_match.group(1)
        body = raw[fm_match.end():]
        try:
            import yaml
            fm_data = yaml.safe_load(yaml_text) or {}
        except Exception:
            logger.warning("Failed to parse YAML frontmatter in %s", path)
            fm_data = {}
    else:
        fm_data = {}
        body = raw

    frontmatter = SkillFrontmatter(
        name=fm_data.get("name") or directory_name,
        description=fm_data.get("description") or "",
        category=fm_data.get("category") or "",
        required_skills=fm_data.get("required_skills") or [],
    )

    return ParsedSkill(
        frontmatter=frontmatter,
        body=body.strip(),
        file_path=str(path),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestration/skill_parser.py backend/tests/test_orchestration/test_skill_parser.py
git commit -m "feat: add SKILL.md parser with YAML frontmatter support"
```

---

### Task 2: Enhanced Skill Model & Registry

**Files:**
- Modify: `backend/app/orchestration/skill_registry.py`
- Modify: `backend/tests/test_orchestration/test_skill_registry.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_orchestration/test_skill_registry.py`:

```python
import pytest
from app.orchestration.skill_registry import SkillRegistry, SkillMetadata


class TestSkillRegistryFileSystemScan:
    def test_scan_skills_dir(self, tmp_path):
        skill_dir = tmp_path / "brainstorming"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: brainstorming\ndescription: "Use when exploring ideas."\n---\n\n# Brainstorming\n',
            encoding="utf-8",
        )

        registry = SkillRegistry()
        registry.scan_directory(tmp_path)

        skill = registry.get_skill("brainstorming")
        assert skill is not None
        assert skill.description == "Use when exploring ideas."

    def test_scan_multiple_dirs(self, tmp_path):
        dir_a = tmp_path / "dir_a"
        dir_b = tmp_path / "dir_b"
        dir_a.mkdir()
        dir_b.mkdir()

        (dir_a / "skill-a" / "SKILL.md").parent.mkdir()
        (dir_a / "skill-a" / "SKILL.md").write_text(
            '---\nname: skill-a\ndescription: "Skill A"\n---\n\n# A\n', encoding="utf-8"
        )
        (dir_b / "skill-b" / "SKILL.md").parent.mkdir()
        (dir_b / "skill-b" / "SKILL.md").write_text(
            '---\nname: skill-b\ndescription: "Skill B"\n---\n\n# B\n', encoding="utf-8"
        )

        registry = SkillRegistry()
        registry.scan_directory(dir_a)
        registry.scan_directory(dir_b)

        assert registry.get_skill("skill-a") is not None
        assert registry.get_skill("skill-b") is not None

    def test_get_skill_content_lazy(self, tmp_path):
        skill_dir = tmp_path / "tdd"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: test-driven-development\ndescription: "Use for TDD."\n---\n\n# TDD\n\nWrite test first.\n',
            encoding="utf-8",
        )

        registry = SkillRegistry()
        registry.scan_directory(tmp_path)

        metadata = registry.get_skill("test-driven-development")
        assert metadata is not None
        assert metadata.content_loaded is False

        content = registry.get_skill_content("test-driven-development")
        assert "Write test first" in content
        assert metadata.content_loaded is True

    def test_scan_skips_invalid_dirs(self, tmp_path):
        (tmp_path / "not-a-skill").mkdir()
        (tmp_path / "not-a-skill" / "README.md").write_text("No SKILL.md here", encoding="utf-8")

        registry = SkillRegistry()
        registry.scan_directory(tmp_path)

        assert len(registry.list_skills()) == 0

    def test_skill_metadata_fields(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            '---\nname: my-skill\ndescription: "Test skill"\ncategory: technique\nrequired_skills:\n  - brainstorming\n---\n\n# My Skill\n',
            encoding="utf-8",
        )

        registry = SkillRegistry()
        registry.scan_directory(tmp_path)

        skill = registry.get_skill("my-skill")
        assert skill.category == "technique"
        assert skill.required_skills == ["brainstorming"]
        assert skill.file_path == str(skill_dir / "SKILL.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_registry.py::TestSkillRegistryFileSystemScan -v`
Expected: FAIL — `ImportError: cannot import name 'SkillMetadata'`

- [ ] **Step 3: Write minimal implementation**

Replace `backend/app/orchestration/skill_registry.py` with:

```python
import logging
from pathlib import Path

from pydantic import BaseModel

from app.orchestration.skill_parser import parse_skill_md

logger = logging.getLogger(__name__)


class SkillMetadata(BaseModel):
    name: str
    description: str
    category: str = ""
    required_skills: list[str] = []
    file_path: str = ""
    enabled: bool = True
    content_loaded: bool = False


class SkillRegistry:
    def __init__(self):
        self.skills: dict[str, SkillMetadata] = {}
        self._content_cache: dict[str, str] = {}
        logger.info("技能注册中心初始化完成")

    def scan_directory(self, dir_path: Path | str) -> int:
        dir_path = Path(dir_path)
        if not dir_path.exists() or not dir_path.is_dir():
            logger.warning("技能目录不存在: %s", dir_path)
            return 0

        count = 0
        for child in sorted(dir_path.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                parsed = parse_skill_md(skill_file)
                fm = parsed.frontmatter
                metadata = SkillMetadata(
                    name=fm.name,
                    description=fm.description,
                    category=fm.category,
                    required_skills=fm.required_skills,
                    file_path=parsed.file_path,
                )
                self.skills[metadata.name] = metadata
                self._content_cache[metadata.name] = parsed.body
                metadata.content_loaded = True
                count += 1
                logger.info("发现技能: %s (category=%s)", metadata.name, metadata.category)
            except Exception:
                logger.exception("解析技能失败: %s", skill_file)
        return count

    def register_skill(self, skill: SkillMetadata) -> None:
        self.skills[skill.name] = skill
        logger.info("注册技能: %s", skill.name)

    def unregister_skill(self, name: str) -> bool:
        if name in self.skills:
            del self.skills[name]
            self._content_cache.pop(name, None)
            logger.info("注销技能: %s", name)
            return True
        return False

    def get_skill(self, name: str) -> SkillMetadata | None:
        return self.skills.get(name)

    def get_skill_content(self, name: str) -> str | None:
        skill = self.skills.get(name)
        if skill is None:
            return None
        if name in self._content_cache:
            return self._content_cache[name]
        if skill.file_path and Path(skill.file_path).exists():
            parsed = parse_skill_md(skill.file_path)
            self._content_cache[name] = parsed.body
            skill.content_loaded = True
            return parsed.body
        return None

    def list_skills(self) -> list[SkillMetadata]:
        return list(self.skills.values())

    def list_enabled_skills(self) -> list[SkillMetadata]:
        return [s for s in self.skills.values() if s.enabled]

    def list_skills_by_category(self, category: str) -> list[SkillMetadata]:
        return [s for s in self.skills.values() if s.category == category]

    def enable_skill(self, name: str) -> bool:
        skill = self.get_skill(name)
        if skill:
            skill.enabled = True
            logger.info("启用技能: %s", name)
            return True
        return False

    def disable_skill(self, name: str) -> bool:
        skill = self.get_skill(name)
        if skill:
            skill.enabled = False
            logger.info("禁用技能: %s", name)
            return True
        return False


skill_registry = SkillRegistry()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_registry.py -v`
Expected: PASS (all tests, both old and new)

- [ ] **Step 5: Update old tests to match new model**

The old tests reference `Skill(name=..., description=..., tools=..., prompt_template=...)`. Update them to use `SkillMetadata(name=..., description=...)` and adjust assertions accordingly.

- [ ] **Step 6: Run all skill tests**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_registry.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/orchestration/skill_registry.py backend/tests/test_orchestration/test_skill_registry.py
git commit -m "feat: enhanced SkillRegistry with filesystem scanning and lazy content loading"
```

---

### Task 3: Skill Settings & Auto-Scan at Startup

**Files:**
- Modify: `backend/app/config/settings.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_orchestration/test_skill_registry.py`:

```python
class TestSkillRegistryAutoScan:
    def test_scan_default_dirs(self, tmp_path, monkeypatch):
        local_skills = tmp_path / "project" / "skills"
        local_skills.mkdir(parents=True)
        (local_skills / "demo" / "SKILL.md").parent.mkdir()
        (local_skills / "demo" / "SKILL.md").write_text(
            '---\nname: demo\ndescription: "Demo skill"\n---\n\n# Demo\n', encoding="utf-8"
        )

        global_skills = tmp_path / "global_skills"
        global_skills.mkdir()
        (global_skills / "global-skill" / "SKILL.md").parent.mkdir()
        (global_skills / "global-skill" / "SKILL.md").write_text(
            '---\nname: global-skill\ndescription: "Global skill"\n---\n\n# Global\n', encoding="utf-8"
        )

        registry = SkillRegistry()
        registry.scan_directory(local_skills)
        registry.scan_directory(global_skills)

        assert registry.get_skill("demo") is not None
        assert registry.get_skill("global-skill") is not None
```

- [ ] **Step 2: Run test to verify it passes** (this test is compatible with current code)

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_registry.py::TestSkillRegistryAutoScan -v`
Expected: PASS

- [ ] **Step 3: Add SkillSettings to config**

In `backend/app/config/settings.py`, add:

```python
class SkillSettings(BaseModel):
    """技能配置"""
    scan_dirs: list[str] = Field(default_factory=list)
    auto_scan: bool = True
```

Add `skill: SkillSettings = SkillSettings()` to `AppSettings`.

- [ ] **Step 4: Wire auto-scan into app startup**

In `backend/app/main.py`, add to the `lifespan` function after `agent_service.start_background_tasks()`:

```python
from app.orchestration.skill_registry import skill_registry
from app.config.settings import config_manager

skill_settings = config_manager.settings.skill
if skill_settings.auto_scan:
    project_skills = Path.cwd() / "skills"
    if project_skills.exists():
        skill_registry.scan_directory(project_skills)
    global_skills = Path.home() / ".reflexion" / "skills"
    if global_skills.exists():
        skill_registry.scan_directory(global_skills)
    for extra_dir in skill_settings.scan_dirs:
        p = Path(extra_dir)
        if p.exists():
            skill_registry.scan_directory(p)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_orchestration/test_skill_registry.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/config/settings.py backend/app/main.py
git commit -m "feat: add SkillSettings and auto-scan skills at startup"
```

---

### Task 4: Enhanced Skills API Routes

**Files:**
- Modify: `backend/app/api/routes/skills.py`
- Test: modify `backend/tests/test_orchestration/test_skill_registry.py` (or create API test)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_api/test_skills_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.skill_registry import SkillMetadata, skill_registry


@pytest.fixture(autouse=True)
def _reset_registry():
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()
    yield
    skill_registry.skills.clear()
    skill_registry._content_cache.clear()


client = TestClient(app)


class TestSkillsAPI:
    def test_list_skills_empty(self):
        resp = client.get("/api/skills/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_skills_with_data(self):
        skill_registry.register_skill(
            SkillMetadata(name="test-skill", description="A test skill", category="technique")
        )

        resp = client.get("/api/skills/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-skill"
        assert "content" not in data[0]

    def test_get_skill_detail(self):
        skill_registry.register_skill(
            SkillMetadata(name="detail-skill", description="Detail", file_path="/fake/SKILL.md")
        )
        skill_registry._content_cache["detail-skill"] = "# Detail Skill\n\nFull content here."

        resp = client.get("/api/skills/detail-skill")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "detail-skill"
        assert "Full content here" in data["content"]

    def test_get_skill_detail_not_found(self):
        resp = client.get("/api/skills/nonexistent")
        assert resp.status_code == 404

    def test_enable_skill(self):
        skill_registry.register_skill(
            SkillMetadata(name="toggle-skill", description="Toggle", enabled=False)
        )

        resp = client.post("/api/skills/toggle-skill/enable")
        assert resp.status_code == 200
        assert skill_registry.get_skill("toggle-skill").enabled is True

    def test_disable_skill(self):
        skill_registry.register_skill(
            SkillMetadata(name="toggle-skill", description="Toggle", enabled=True)
        )

        resp = client.post("/api/skills/toggle-skill/disable")
        assert resp.status_code == 200
        assert skill_registry.get_skill("toggle-skill").enabled is False

    def test_categories_endpoint(self):
        skill_registry.register_skill(
            SkillMetadata(name="a", description="A", category="discipline")
        )
        skill_registry.register_skill(
            SkillMetadata(name="b", description="B", category="technique")
        )
        skill_registry.register_skill(
            SkillMetadata(name="c", description="C", category="discipline")
        )

        resp = client.get("/api/skills/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert "discipline" in data
        assert "technique" in data
        assert len(data["discipline"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api/test_skills_api.py -v`
Expected: FAIL — 404 on new endpoints

- [ ] **Step 3: Write minimal implementation**

Replace `backend/app/api/routes/skills.py`:

```python
from fastapi import APIRouter, HTTPException

from app.orchestration.skill_registry import skill_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/")
async def list_skills():
    metadata_list = skill_registry.list_skills()
    return [
        {
            "name": s.name,
            "description": s.description,
            "category": s.category,
            "required_skills": s.required_skills,
            "enabled": s.enabled,
        }
        for s in metadata_list
    ]


@router.get("/categories")
async def list_categories():
    result: dict[str, list[dict]] = {}
    for skill in skill_registry.list_skills():
        cat = skill.category or "uncategorized"
        result.setdefault(cat, []).append({
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
        })
    return result


@router.get("/{skill_name}")
async def get_skill_detail(skill_name: str):
    skill = skill_registry.get_skill(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")

    content = skill_registry.get_skill_content(skill_name)
    return {
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "required_skills": skill.required_skills,
        "enabled": skill.enabled,
        "content": content or "",
    }


@router.post("/{skill_name}/enable")
async def enable_skill(skill_name: str):
    ok = skill_registry.enable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": True}


@router.post("/{skill_name}/disable")
async def disable_skill(skill_name: str):
    ok = skill_registry.disable_skill(skill_name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"name": skill_name, "enabled": False}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_api/test_skills_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/skills.py backend/tests/test_api/test_skills_api.py
git commit -m "feat: enhanced skills API with detail, enable/disable, categories endpoints"
```

---

### Task 5: Skill Tool for LLM Agent

**Files:**
- Create: `backend/app/tools/skill_tool.py`
- Test: create or extend tool tests

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tools/test_skill_tool.py`:

```python
import pytest
from app.tools.skill_tool import SkillTool
from app.orchestration.skill_registry import SkillMetadata, SkillRegistry


@pytest.fixture
def registry():
    r = SkillRegistry()
    r.register_skill(
        SkillMetadata(
            name="brainstorming",
            description="Use when exploring ideas.",
            category="discipline",
            file_path="/fake/SKILL.md",
        )
    )
    r._content_cache["brainstorming"] = "# Brainstorming\n\nHelp turn ideas into designs."
    return r


class TestSkillTool:
    def test_list_skills(self, registry):
        tool = SkillTool(registry)
        schema = tool.get_schema()
        assert schema["name"] == "skill"

    def test_execute_list(self, registry):
        tool = SkillTool(registry)
        result = tool.execute({"action": "list"})
        assert result.success
        assert "brainstorming" in result.output

    def test_execute_load(self, registry):
        tool = SkillTool(registry)
        result = tool.execute({"action": "load", "name": "brainstorming"})
        assert result.success
        assert "Help turn ideas into designs" in result.output

    def test_execute_load_not_found(self, registry):
        tool = SkillTool(registry)
        result = tool.execute({"action": "load", "name": "nonexistent"})
        assert result.success is False

    def test_execute_search(self, registry):
        tool = SkillTool(registry)
        result = tool.execute({"action": "search", "query": "exploring"})
        assert result.success
        assert "brainstorming" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tools/test_skill_tool.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/tools/skill_tool.py`:

```python
import json
import logging

from app.orchestration.skill_registry import SkillRegistry
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SkillTool(BaseTool):
    name = "skill"
    description = "Discover and load skill guides. Use 'list' to see available skills, 'load' to read a skill's full content, 'search' to find skills by keyword."

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "load", "search"],
                        "description": "Action: 'list' all skills, 'load' a skill's content, 'search' by keyword",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name (required for 'load' action)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search keyword (required for 'search' action)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(self, args: dict) -> ToolResult:
        action = args.get("action", "list")

        if action == "list":
            skills = self._registry.list_enabled_skills()
            lines = []
            for s in skills:
                req = f" (requires: {', '.join(s.required_skills)})" if s.required_skills else ""
                lines.append(f"- {s.name}: {s.description}{req}")
            output = "Available skills:\n" + "\n".join(lines) if lines else "No skills available."
            return ToolResult(success=True, output=output)

        if action == "load":
            skill_name = args.get("name", "")
            content = self._registry.get_skill_content(skill_name)
            if content is None:
                return ToolResult(success=False, error=f"Skill not found: {skill_name}")
            skill = self._registry.get_skill(skill_name)
            header = f"# {skill.name}\n\n> {skill.description}\n\n"
            return ToolResult(success=True, output=header + content)

        if action == "search":
            query = (args.get("query") or "").lower()
            if not query:
                return ToolResult(success=False, error="Search query is required")
            matches = []
            for s in self._registry.list_enabled_skills():
                searchable = f"{s.name} {s.description} {s.category}".lower()
                if query in searchable:
                    matches.append(f"- {s.name}: {s.description}")
            output = "Matching skills:\n" + "\n".join(matches) if matches else "No skills match the query."
            return ToolResult(success=True, output=output)

        return ToolResult(success=False, error=f"Unknown action: {action}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_tools/test_skill_tool.py -v`
Expected: PASS

- [ ] **Step 5: Register SkillTool in AgentService**

In `backend/app/services/agent_service.py`, add import and register in `_build_run_tool_registry`:

```python
from app.orchestration.skill_registry import skill_registry as global_skill_registry
from app.tools.skill_tool import SkillTool
```

In `_build_run_tool_registry`, after existing `registry.register(...)` calls:

```python
registry.register(SkillTool(global_skill_registry))
```

- [ ] **Step 6: Run all tests**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/tools/skill_tool.py backend/tests/test_tools/test_skill_tool.py backend/app/services/agent_service.py
git commit -m "feat: add LLM-callable skill tool for agent skill discovery and loading"
```

---

### Task 6: Skill Content Injection into System Prompt

**Files:**
- Modify: `backend/app/memory/context_assembly.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_memory/test_context_assembly.py` (or create):

```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from app.memory.context_assembly import ContextAssembler
from app.orchestration.skill_registry import SkillMetadata, SkillRegistry


class TestContextAssemblerSkills:
    def test_enabled_skills_injected_into_system_sections(self, tmp_path):
        registry = SkillRegistry()
        registry.register_skill(
            SkillMetadata(
                name="tdd",
                description="Use when implementing features",
                category="discipline",
                enabled=True,
                file_path="/fake/SKILL.md",
            )
        )
        registry._content_cache["tdd"] = "# TDD\n\nWrite test first."

        registry.register_skill(
            SkillMetadata(
                name="disabled-skill",
                description="Disabled",
                enabled=False,
                file_path="/fake2/SKILL.md",
            )
        )
        registry._content_cache["disabled-skill"] = "# Disabled\n\nShould not appear."

        conv_service = MagicMock()
        conv_service.get_latest_continuation_artifact.return_value = None
        conv_service.list_recent_seed_candidates.return_value = []

        assembler = ContextAssembler(
            conversation_service=conv_service,
            skill_registry=registry,
        )

        result = assembler.build_for_session(
            session_id="s1",
            project_id="p1",
            project_path=str(tmp_path),
        )

        skill_sections = [s for s in result.system_sections if "TDD" in s or "skill" in s.lower()]
        assert any("Write test first" in s for s in skill_sections)
        assert not any("Should not appear" in s for s in result.system_sections)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_memory/test_context_assembly.py -v`
Expected: FAIL — `ContextAssembler` doesn't accept `skill_registry` param yet

- [ ] **Step 3: Write minimal implementation**

In `backend/app/memory/context_assembly.py`, modify `ContextAssembler.__init__` to accept optional `skill_registry`:

```python
from app.orchestration.skill_registry import SkillRegistry


class ContextAssembler:
    def __init__(
        self,
        *,
        conversation_service: ConversationService,
        curated_store: CuratedMemoryStore | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.conversation_service = conversation_service
        self.curated_store = curated_store or CuratedMemoryStore()
        self.skill_registry = skill_registry
```

In `build_for_session`, after the AGENTS.md block and before curated memory:

```python
if self.skill_registry:
    enabled_skills = self.skill_registry.list_enabled_skills()
    if enabled_skills:
        skill_section_parts = ["## Available Skills\n"]
        skill_section_parts.append(
            "You have access to the following skills. Use the 'skill' tool with action='load' "
            "to read a skill's full content before following its guidance.\n"
        )
        for s in enabled_skills:
            req = f" (requires: {', '.join(s.required_skills)})" if s.required_skills else ""
            skill_section_parts.append(f"- **{s.name}**: {s.description}{req}")
        static_blocks.append("\n".join(skill_section_parts))
```

Update `AgentService.__init__` to pass `skill_registry` to `ContextAssembler`:

```python
from app.orchestration.skill_registry import skill_registry as global_skill_registry

self.context_assembler = ContextAssembler(
    conversation_service=self.conversation_service,
    skill_registry=global_skill_registry,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_memory/test_context_assembly.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory/context_assembly.py backend/app/services/agent_service.py
git commit -m "feat: inject enabled skill metadata into LLM system prompt context"
```

---

### Task 7: Frontend Skill Type & API Updates

**Files:**
- Modify: `frontend/src/types/skill.ts`
- Modify: `frontend/src/features/skills/skillApi.ts`

- [ ] **Step 1: Update Skill type**

Replace `frontend/src/types/skill.ts`:

```typescript
export interface Skill {
  name: string
  description: string
  category: string
  required_skills: string[]
  enabled: boolean
}

export interface SkillDetail extends Skill {
  content: string
}

export interface SkillCategories {
  [category: string]: { name: string; description: string; enabled: boolean }[]
}
```

- [ ] **Step 2: Update skill API**

Replace `frontend/src/features/skills/skillApi.ts`:

```typescript
import { apiClient } from '@/services/apiClient'
import type { Skill, SkillDetail, SkillCategories } from '@/types/skill'

export const skillApi = {
  list: () => apiClient.get<Skill[]>('/api/skills'),
  detail: (name: string) => apiClient.get<SkillDetail>(`/api/skills/${name}`),
  categories: () => apiClient.get<SkillCategories>('/api/skills/categories'),
  enable: (name: string) => apiClient.post(`/api/skills/${name}/enable`),
  disable: (name: string) => apiClient.post(`/api/skills/${name}/disable`),
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (or fix type errors in dependent files)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/skill.ts frontend/src/features/skills/skillApi.ts
git commit -m "feat: extend frontend skill types and API with detail, categories, enable/disable"
```

---

### Task 8: Frontend SkillsPage Redesign

**Files:**
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: Write the redesigned SkillsPage**

Replace `frontend/src/pages/SkillsPage.tsx` with a redesigned version that includes:
- Category tabs/sidebar (discipline, technique, pattern, reference, uncategorized)
- Skill cards with description, category badge, required-skills chips, enabled toggle
- Click-to-expand detail drawer showing full SKILL.md content
- Enable/disable toggle per skill
- Search bar for filtering skills

The implementation should follow existing component patterns from other pages in the project (check `frontend/src/pages/` for reference on layout, styling conventions).

Key behavior:
- On mount: call `skillApi.list()` and `skillApi.categories()`
- Click skill card: call `skillApi.detail(name)`, show content in a side panel/drawer
- Toggle switch: call `skillApi.enable/disable`, update local state
- Category tabs filter the displayed list

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "feat: redesign SkillsPage with categories, detail view, and enable/disable"
```

---

### Task 9: Migrate Existing Skill & Add Default Skills

**Files:**
- Modify: `skills/code-implementation-discipline/SKILL.md` (add YAML frontmatter)
- Create: `skills/brainstorming/SKILL.md`
- Create: `skills/systematic-debugging/SKILL.md`
- Create: `skills/test-driven-development/SKILL.md`
- Create: `skills/verification-before-completion/SKILL.md`

- [ ] **Step 1: Add YAML frontmatter to existing skill**

The existing `skills/code-implementation-discipline/SKILL.md` already has frontmatter. Verify it matches the new schema (add `category: discipline` if missing).

- [ ] **Step 2: Create new skill files**

Create each skill with appropriate YAML frontmatter following opencode's SKILL.md convention:
- `name` and `description` in frontmatter
- `description` starts with "Use when..." and only describes triggering conditions
- `category` field: discipline | technique | pattern | reference
- Body follows the standard structure: Overview, When to Use, Decision Gates, Common Mistakes, Red Flags

These are ported/adapted from opencode's superpowers skills but simplified for ReflexionOS's agent loop.

- [ ] **Step 3: Verify backend scans them**

Run: `cd backend && python -c "from app.orchestration.skill_registry import SkillRegistry; r = SkillRegistry(); r.scan_directory('../skills'); print(r.list_skills())"`
Expected: Lists all 5 skills

- [ ] **Step 4: Commit**

```bash
git add skills/
git commit -m "feat: add default skills with YAML frontmatter matching opencode convention"
```

---

### Task 10: Integration Test & Cleanup

**Files:**
- Various cleanup

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 2: Run full frontend build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Remove old `Skill` model references**

Search for any remaining references to the old `Skill(name, tools, prompt_template)` pattern and update them.

- [ ] **Step 4: Run backend lint**

Run: `cd backend && python -m ruff check app/ tests/`
Expected: No errors

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: cleanup after skills system enhancement"
```
