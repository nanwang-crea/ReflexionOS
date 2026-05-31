# Plugin + Skill System Full Alignment with OpenCode

**Date:** 2026-05-31
**Status:** Design

## Goal

Replace ReflexionOS's current skill-only system with a full plugin pipeline that matches OpenCode's architecture: declarative config → package resolution → plugin loading → multi-path skill discovery → dynamic tool description injection.

## Why Replace (Not Extend)

The current system has fundamental design problems:

1. **SkillInstaller duplicates PackageResolver** — `git clone` into `~/.reflexion/skills/` is a poor man's package manager. No versioning, no caching, no update detection, no multi-package support.
2. **No plugin concept** — Superpowers can only contribute skills, not tools/hooks. OpenCode plugins register JS entry points that add tools, hooks, and skills.
3. **scan_directory only goes one level deep** — A cloned repo like superpowers has `skills/brainstorming/SKILL.md` but `scan_directory` only looks at direct children.
4. **SkillTool description is static** — OpenCode injects `<available_skills>` XML into the tool description so the LLM sees skills without calling `list` first. ReflexionOS doesn't do this.
5. **Only two scan paths** — Project `skills/` and `~/.reflexion/skills/`. OpenCode scans 6+ paths including plugin-internal skill directories.
6. **Install is only runtime** — No declarative config (`"plugins": [...]`), only `skill — action: install` at runtime.

## Architecture

```
config.json: "plugins": ["superpowers@git+https://github.com/obra/superpowers.git"]
       │
       ▼
┌─────────────────────────────────────────┐
│ PackageResolver (startup)               │
│                                         │
│ 1. Parse "name@spec" specifiers         │
│ 2. Resolve: git clone (shallow) or      │
│    pip install or local path symlink    │
│ 3. Cache in ~/.reflexion/packages/      │
│ 4. Version pin: #v5.0.3 → --branch     │
│ 5. Update detection: git ls-remote vs   │
│    local HEAD → re-clone if changed     │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ PluginLoader                            │
│                                         │
│ 1. For each resolved package:           │
│    a. Check for reflexion_plugin.py     │
│    b. If exists → import, call register │
│       → get PluginRegistration          │
│    c. If not → auto-discover skills/    │
│       subdirectories (pure skill packs) │
│ 2. Collect: custom tools, hooks,        │
│    skill directories, config schemas    │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ SkillRegistry (rewritten scan)          │
│                                         │
│ Scan paths (in priority order):         │
│ 1. Project: ./skills/                   │
│ 2. Project: ./.reflexion/skills/        │
│ 3. Global: ~/.reflexion/skills/         │
│ 4. Plugin: each package's skills/ dir   │
│ 5. Compat: ~/.agents/skills/            │
│ 6. Config: skill.scan_dirs              │
│                                         │
│ Recursive scan: find SKILL.md at any   │
│ depth under a given root, not just      │
│ direct children.                        │
│                                         │
│ Source tracking: each skill records     │
│ where it came from (project/global/     │
│ plugin/compat) and which plugin owns it │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ SkillTool (dynamic description)         │
│                                         │
│ Tool description includes               │
│ <available_skills> XML block listing    │
│ all enabled skills with name/desc/loc.  │
│ LLM sees skills without calling list.   │
│                                         │
│ Actions: list, load, search, update      │
└─────────────────────────────────────────┘
```

## Core Components

### 1. PackageSpecifier + PackageResolver

**File:** `backend/app/orchestration/package_resolver.py` (NEW — replaces `skill_installer.py`)

**Specifier format:**

| Specifier | type | name | url | ref |
|-----------|------|------|-----|-----|
| `superpowers@git+https://github.com/obra/superpowers.git` | git | superpowers | https://github.com/obra/superpowers.git | main |
| `superpowers@git+https://github.com/obra/superpowers.git#v5.0.3` | git | superpowers | https://github.com/obra/superpowers.git | v5.0.3 |
| `my-plugin@file:///local/path` | local | my-plugin | /local/path | — |
| `my-pypi-plugin` | pypi | my-pypi-plugin | my-pypi-plugin | latest |

> **Note:** PyPI resolution is deferred to a future spec. The `pypi` spec_type is defined in the data model for forward compatibility but `PackageResolver.resolve()` will return an error for pypi specifiers in this implementation. Only `git` and `local` are supported now.

**Data model:**

```python
class PackageSpecifier(BaseModel):
    raw: str
    name: str
    spec_type: Literal["git", "local", "pypi"]
    url: str
    ref: str = "main"

    @classmethod
    def parse(cls, raw: str) -> "PackageSpecifier":
        # "name@git+https://...#ref" → split and parse
        # "name@file:///..." → local
        # "name" → pypi

class ResolvedPackage(BaseModel):
    specifier: PackageSpecifier
    install_path: str          # ~/.reflexion/packages/{name}/
    resolved_ref: str          # actual git commit hash or version
    has_plugin_entry: bool
    skill_dirs: list[str]      # relative paths to skill dirs within package
    metadata: dict             # package.json or pyproject.toml fields if present
```

**PackageResolver methods:**

```python
class PackageResolver:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir  # ~/.reflexion/packages/

    def resolve(self, spec: PackageSpecifier) -> ResolvedPackage:
        # git: clone --depth=1 --branch={ref} into cache_dir/{name}/
        #      if already cloned: check if ref matches (update detection)
        # local: symlink into cache_dir/{name}/
        # pypi: pip install into cache_dir/{name}/ (future)
        # After install: scan for reflexion_plugin.py and skills/ dirs

    def resolve_all(self, specs: list[str]) -> list[ResolvedPackage]:
        return [self.resolve(PackageSpecifier.parse(s)) for s in specs]

    def is_update_available(self, spec: PackageSpecifier) -> bool:
        # git ls-remote HEAD vs local HEAD commit

    def update(self, spec: PackageSpecifier) -> ResolvedPackage:
        # rm -rf cache, re-clone

    def remove(self, name: str) -> bool:
        # rm -rf cache_dir/{name}/
```

### 2. PluginLoader

**File:** `backend/app/orchestration/plugin_loader.py` (NEW)

**Plugin entry point protocol:**

A plugin package MAY contain a `reflexion_plugin.py` at its root:

```python
# reflexion_plugin.py — written by plugin author
def register():
    return {
        "tools": [],              # list of BaseTool instances or tool schema dicts
        "hooks": {},              # {"event_name": callable}
        "skill_dirs": ["skills"], # relative paths to skill directories
        "config_schema": None,    # optional JSON schema for plugin config
    }
```

For pure skill packages (like superpowers) that lack `reflexion_plugin.py`, PluginLoader auto-discovers any directory containing `SKILL.md` files.

```python
class PluginRegistration(BaseModel):
    plugin_name: str
    tools: list[dict]           # tool schema dicts (BaseTool instances converted at load time)
    skill_dirs: list[str]       # absolute paths to skill directories
    config_schema: dict | None

class PluginLoader:
    def __init__(self, resolver: PackageResolver):
        self._resolver = resolver
        self._registrations: dict[str, PluginRegistration] = {}
        self._hook_registry: dict[str, list[Callable]] = {}  # stored separately, not in Pydantic model

    def load_plugin(self, package: ResolvedPackage) -> PluginRegistration | None:
        entry_path = Path(package.install_path) / "reflexion_plugin.py"
        if entry_path.exists():
            # dynamic import
            spec = importlib.util.spec_from_file_location(
                f"reflexion_plugin_{package.specifier.name}", str(entry_path)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            reg_data = module.register()
            # build PluginRegistration from reg_data
        else:
            # auto-discover: find all dirs containing SKILL.md
            skill_dirs = self._auto_discover_skills(package.install_path)
            # build minimal PluginRegistration with just skill_dirs

    def load_all(self, packages: list[ResolvedPackage]) -> list[PluginRegistration]:
        return [r for r in (self.load_plugin(p) for p in packages) if r is not None]

    def _auto_discover_skills(self, root: str) -> list[str]:
        # walk root, find directories that contain SKILL.md
        # return list of parent directories (one per skill)

    def get_all_skill_dirs(self) -> list[str]:
        return [d for r in self._registrations.values() for d in r.skill_dirs]

    def get_hook(self, event: str) -> list[Callable]:
        return self._hook_registry.get(event, [])
```

### 3. SkillRegistry (Rewrite)

**File:** `backend/app/orchestration/skill_registry.py` (REPLACE)

**Key changes from current:**

- Remove `get_installer()` / `install_skill()` / `uninstall_skill()` — these move to PackageResolver and plugin API
- Add `scan_recursive()` — walk directory tree to find `SKILL.md` at any depth
- Add `scan_all()` — unified scan of all configured paths
- Add source tracking (`SkillSource` enum)
- Remove `SkillInstaller` dependency

```python
from enum import Enum

class SkillSource(str, Enum):
    PROJECT = "project"        # ./skills/
    PROJECT_REFLEXION = "project_reflexion"  # ./.reflexion/skills/
    GLOBAL = "global"          # ~/.reflexion/skills/
    PLUGIN = "plugin"          # plugin package internal
    COMPAT = "compat"          # ~/.agents/skills/ etc
    CONFIG = "config"          # scan_dirs entries

class SkillMetadata(BaseModel):
    name: str
    description: str
    category: str = ""
    required_skills: list[str] = []
    file_path: str = ""
    source: str = ""            # git URL or source identifier
    source_type: SkillSource = SkillSource.PROJECT
    install_path: str = ""
    plugin_name: str = ""       # which plugin provided this skill
    enabled: bool = True
    content_loaded: bool = False
    version: str = ""           # git commit hash if from plugin

class SkillRegistry:
    def __init__(self):
        self.skills: dict[str, SkillMetadata] = {}
        self._content_cache: dict[str, str] = {}

    def scan_directory(self, dir_path: Path | str) -> int:
        # UNCHANGED: scan direct children for SKILL.md

    def scan_recursive(self, dir_path: Path | str,
                       source_type: SkillSource = SkillSource.PROJECT,
                       plugin_name: str = "") -> int:
        # Walk dir_path recursively, find any SKILL.md at any depth
        # For each found SKILL.md:
        #   - parse frontmatter
        #   - create SkillMetadata with source_type, plugin_name
        #   - register

    def scan_all(self, plugin_skill_dirs: list[str] | None = None) -> int:
        # 1. Project: ./skills/
        # 2. Project: ./.reflexion/skills/
        # 3. Global: ~/.reflexion/skills/
        # 4. Plugin: each dir in plugin_skill_dirs
        # 5. Compat: ~/.agents/skills/, ~/.claude/skills/
        # 6. Config: scan_dirs

    def register_skill(self, skill: SkillMetadata) -> None: ...
    def unregister_skill(self, name: str) -> bool: ...
    def get_skill(self, name: str) -> SkillMetadata | None: ...
    def get_skill_content(self, name: str) -> str | None: ...
    def list_skills(self) -> list[SkillMetadata]: ...
    def list_enabled_skills(self) -> list[SkillMetadata]: ...
    def list_skills_by_category(self, category: str) -> list[SkillMetadata]: ...
    def enable_skill(self, name: str) -> bool: ...
    def disable_skill(self, name: str) -> bool: ...
    def refresh(self) -> int: ...  # calls scan_all()
```

### 4. SkillTool (Rewrite)

**File:** `backend/app/tools/skill_tool.py` (REPLACE)

**Key changes:**

- Dynamic description with `<available_skills>` XML injection (matches OpenCode)
- Remove `install`/`uninstall` actions — these move to plugin API
- Add `update` action for checking plugin updates
- Keep `list`, `load`, `search`

**Token budget for dynamic description:** The `<available_skills>` block is included in every tool schema sent to the LLM. To stay within budget, each skill's description in the XML is truncated to 200 characters. If more than 30 skills are enabled, only the first 30 are listed in the description (the rest are discoverable via `list` action).

```python
class SkillTool(BaseTool):
    def __init__(self, registry: SkillRegistry, plugin_service=None):
        self._registry = registry
        self._plugin_service = plugin_service

    @property
    def name(self) -> str:
        return "skill"

    @property
    def description(self) -> str:
        base = ("Discover and load skill guides. "
                "Use 'list' to see skills, 'load' to read content, "
                "'search' by keyword, 'update' to check for updates.")

        enabled = self._registry.list_enabled_skills()
        if enabled:
            lines = []
            for s in enabled:
                req = f" (requires: {', '.join(s.required_skills)})" if s.required_skills else ""
                lines.append(
                    f"  <skill>\n"
                    f"    <name>{s.name}</name>\n"
                    f"    <description>{s.description}{req}</description>\n"
                    f"    <location>{s.file_path}</location>\n"
                    f"  </skill>"
                )
            base += (f"\n\n<available_skills>\n"
                     + "\n".join(lines)
                     + "\n</available_skills>")
        return base

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,  # dynamic!
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "load", "search", "update"],
                        "description": "Action: 'list' all skills, "
                                        "'load' a skill's content, "
                                        "'search' by keyword, "
                                        "'update' check for plugin updates",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name (for 'load' action)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search keyword (for 'search' action)",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        # list: same as current
        # load: same as current
        # search: same as current
        # update: check all plugins for updates via PackageResolver
```

### 5. SkillInstaller — DELETE

**File:** `backend/app/orchestration/skill_installer.py` (DELETE)

Replaced entirely by `PackageResolver`. The `install`/`uninstall` actions on `SkillTool` are also removed — plugin management goes through the Plugin API.

### 6. Plugin API Routes

**File:** `backend/app/api/routes/plugins.py` (NEW)

```python
router = APIRouter(prefix="/api/plugins", tags=["plugins"])

# GET /api/plugins — list installed plugins
# POST /api/plugins/install — install a plugin from specifier
# DELETE /api/plugins/{name} — uninstall a plugin
# POST /api/plugins/update/{name} — update a specific plugin
# POST /api/plugins/update — update all plugins
# GET /api/plugins/{name}/skills — list skills provided by a plugin
```

### 7. Skills API Routes (Update)

**File:** `backend/app/api/routes/skills.py` (MODIFY)

Remove install/uninstall endpoints (moved to plugins API). Add source_type and plugin_name to response.

### 8. Config Settings (Update)

**File:** `backend/app/config/settings.py` (MODIFY)

```python
class SkillSettings(BaseModel):
    scan_dirs: list[str] = Field(default_factory=list)
    auto_scan: bool = True
    install_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".reflexion" / "skills")
    )
    compat_dirs: list[str] = Field(
        default_factory=lambda: [
            str(Path.home() / ".agents" / "skills"),
        ]
    )

class PluginSettings(BaseModel):
    plugins: list[str] = Field(default_factory=list)
    package_cache_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".reflexion" / "packages")
    )
    auto_update: bool = False

class AppSettings(BaseModel):
    llm: LLMSettings = LLMSettings()
    execution: ExecutionSettings = ExecutionSettings()
    memory: MemorySettings = MemorySettings()
    ui: UISettings = UISettings()
    skill: SkillSettings = SkillSettings()
    plugin: PluginSettings = PluginSettings()
```

### 9. Startup Flow (Update)

**File:** `backend/app/main.py` (MODIFY)

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    agent_service.start_background_tasks()

    from app.config.settings import config_manager
    from app.orchestration.package_resolver import PackageResolver
    from app.orchestration.plugin_loader import PluginLoader
    from app.orchestration.skill_registry import skill_registry

    # 1. Resolve plugins
    plugin_settings = config_manager.settings.plugin
    resolver = PackageResolver(Path(plugin_settings.package_cache_dir))
    packages = []
    if plugin_settings.plugins:
        packages = resolver.resolve_all(plugin_settings.plugins)

    # 2. Load plugins
    loader = PluginLoader(resolver)
    registrations = loader.load_all(packages)
    plugin_skill_dirs = loader.get_all_skill_dirs()

    # 3. Scan skills
    skill_settings = config_manager.settings.skill
    if skill_settings.auto_scan:
        skill_registry.scan_all(plugin_skill_dirs=plugin_skill_dirs)

    # 4. Register plugin custom tools into agent service
    # (deferred — tools registered at tool-registry build time)

    try:
        yield
    finally:
        await agent_service.stop_background_tasks()
```

### 10. AgentService (Update)

**File:** `backend/app/services/agent_service.py` (MODIFY)

- SkillTool receives plugin_service for `update` action
- Plugin custom tools registered into ToolRegistry

### 11. ContextAssembly (No changes needed)

Current skill injection into system prompt works fine. The SkillTool dynamic description is the primary change — skills are now visible in tool description, not just in context assembly static blocks.

### 12. Frontend Changes

**New files:**
- `frontend/src/types/plugin.ts` — Plugin, PluginSpecifier types
- `frontend/src/features/plugins/pluginApi.ts` — Plugin API client

**Modified files:**
- `frontend/src/types/skill.ts` — add source_type, plugin_name, version fields
- `frontend/src/features/skills/skillApi.ts` — remove install/uninstall, add update
- `frontend/src/pages/SkillsPage.tsx` — add Plugin tab, source badges, update button

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `backend/app/orchestration/package_resolver.py` | NEW | Package specifier parsing, git clone, caching, update detection |
| `backend/app/orchestration/plugin_loader.py` | NEW | Plugin entry point loading, auto skill discovery |
| `backend/app/orchestration/skill_installer.py` | DELETE | Replaced by PackageResolver |
| `backend/app/orchestration/skill_registry.py` | REPLACE | Recursive scan, multi-path, source tracking |
| `backend/app/orchestration/skill_parser.py` | KEEP | No changes needed |
| `backend/app/tools/skill_tool.py` | REPLACE | Dynamic description, remove install/uninstall, add update |
| `backend/app/api/routes/plugins.py` | NEW | Plugin management API |
| `backend/app/api/routes/skills.py` | MODIFY | Remove install/uninstall endpoints, add source fields |
| `backend/app/config/settings.py` | MODIFY | Add PluginSettings, SkillSettings.compat_dirs |
| `backend/app/main.py` | MODIFY | Plugin resolution + loading at startup |
| `backend/app/services/agent_service.py` | MODIFY | Plugin tool registration, SkillTool with plugin_service |
| `backend/tests/test_orchestration/test_skill_installer.py` | DELETE | Replaced |
| `backend/tests/test_orchestration/test_skill_registry.py` | REPLACE | New scan methods, source tracking |
| `backend/tests/test_orchestration/test_package_resolver.py` | NEW | Specifier parsing, resolve, update, remove |
| `backend/tests/test_orchestration/test_plugin_loader.py` | NEW | Plugin loading, auto-discovery |
| `backend/tests/test_tools/test_skill_tool.py` | REPLACE | Dynamic description, update action |
| `backend/tests/test_api/test_skills_api_install.py` | DELETE | Replaced by plugin API tests |
| `backend/tests/test_api/test_plugins_api.py` | NEW | Plugin API endpoints |
| `frontend/src/types/plugin.ts` | NEW | Plugin type definitions |
| `frontend/src/types/skill.ts` | MODIFY | Add source_type, plugin_name, version |
| `frontend/src/features/plugins/pluginApi.ts` | NEW | Plugin API client |
| `frontend/src/features/skills/skillApi.ts` | MODIFY | Remove install/uninstall |
| `frontend/src/pages/SkillsPage.tsx` | MODIFY | Plugin management, source badges |

## Delete List

These files/concepts are removed entirely (no backward compat):

- `backend/app/orchestration/skill_installer.py` — PackageResolver handles all installation
- `SkillRegistry.get_installer()` / `install_skill()` / `uninstall_skill()` — moved to plugin pipeline
- `SkillTool` install/uninstall actions — moved to plugin API
- `/api/skills/install` endpoint — moved to `/api/plugins/install`
- `/api/skills/{name}` DELETE endpoint — moved to `/api/plugins/{name}` DELETE
- `test_skill_installer.py` — deleted with the module
- `test_skills_api_install.py` — replaced by `test_plugins_api.py`
