# Installing Superpowers for Reflexion

## Prerequisites

- [ReflexionOS](https://github.com/obra/ReflexionOS) installed and running

## Installation

### Declarative (recommended)

Add superpowers to the `plugins` array in `~/.reflexion/config.json`:

```json
{
  "plugin": {
    "plugins": [
      "superpowers@git+https://github.com/obra/superpowers.git"
    ]
  }
}
```

Restart Reflexion. The package resolver clones the repo into
`~/.reflexion/packages/superpowers/`, discovers all skills, and registers
them automatically.

To pin a specific version:

```json
{
  "plugin": {
    "plugins": [
      "superpowers@git+https://github.com/obra/superpowers.git#v5.0.3"
    ]
  }
}
```

### Runtime

Use the Plugin API to install without editing config:

```
POST /api/plugins/install
{"specifier": "superpowers@git+https://github.com/obra/superpowers.git"}
```

Or use the `skill` tool's `update` action after adding the plugin to config.

Verify by asking: "Tell me about your superpowers"

Reflexion uses its own plugin system. If you also use OpenCode, Claude Code,
or another harness, install Superpowers separately for each one.

## How it works

1. **PackageResolver** parses the specifier, clones the git repo (shallow)
   into `~/.reflexion/packages/{name}/`, and stores the resolved ref
2. **PluginLoader** checks for `reflexion_plugin.py` entry point; if absent,
   auto-discovers `SKILL.md` files recursively within the package
3. **SkillRegistry** scans all configured paths (project, global, plugin,
   compat) and registers discovered skills with source tracking

## Usage

Use Reflexion's native `skill` tool:

```
skill — action: list
skill — action: load, name: brainstorming
skill — action: search, query: debugging
skill — action: update
```

The skill tool's description dynamically includes an `<available_skills>`
XML block listing all enabled skills — the LLM sees available skills
without needing to call `list` first.

## Updating

### Auto-update on startup

Set `auto_update: true` in config:

```json
{
  "plugin": {
    "plugins": ["superpowers@git+https://github.com/obra/superpowers.git"],
    "auto_update": true
  }
}
```

### Manual update

```
POST /api/plugins/update/superpowers
```

Or use the `skill` tool:

```
skill — action: update
```

## Uninstalling

```
DELETE /api/plugins/superpowers
```

This removes the package from `~/.reflexion/packages/` and unregisters all
skills provided by the plugin.

## Configuration

### Plugin settings (`~/.reflexion/config.json`)

- `plugin.plugins`: List of plugin specifier strings
- `plugin.package_cache_dir`: Where packages are cached (default: `~/.reflexion/packages/`)
- `plugin.auto_update`: Auto-update plugins on startup (default: `false`)

### Skill settings

- `skill.install_dir`: Where manually placed skills live (default: `~/.reflexion/skills/`)
- `skill.scan_dirs`: Extra directories to scan for skills
- `skill.compat_dirs`: Compatibility directories (default: `~/.agents/skills/`)
- `skill.auto_scan`: Whether to auto-scan on startup (default: `true`)

### Scan paths (in priority order)

1. Project: `./skills/`
2. Project: `./.reflexion/skills/`
3. Global: `~/.reflexion/skills/`
4. Plugin: each installed package's skill directories
5. Compat: `~/.agents/skills/`
6. Config: `skill.scan_dirs`

## Troubleshooting

### Plugin not loading

1. Check logs for resolve/load errors
2. Verify the specifier format: `name@git+https://...git`
3. Make sure `git` is available on your system PATH

### Skills not found after install

1. Restart Reflexion to trigger a fresh scan
2. Call `POST /api/skills/refresh` to rescan without restart
3. Check that the package contains `SKILL.md` files:
   `ls ~/.reflexion/packages/superpowers/`

### Update not picking up new commits

The package resolver caches by ref. If you pinned `#main` and the remote
`main` branch has new commits, the resolver compares `git ls-remote` HEAD
with the local `.commit` file. If they differ, it re-clones.

### Tool mapping

When skills reference Claude Code tools:
- `TodoWrite` → `todowrite`
- `Task` with subagents → Reflexion's agent loop with plan steps
- `Skill` tool → Reflexion's native `skill` tool
- File operations → Reflexion's `file`, `edit`, `glob`, `grep` tools

## Getting Help

- Report issues: https://github.com/obra/superpowers/issues
- ReflexionOS repo: https://github.com/obra/ReflexionOS
