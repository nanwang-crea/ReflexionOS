# Shell Security: Effect Classification + OS Sandbox Redesign

**Date:** 2026-05-03
**Status:** Approved (v2 — revised sandbox downgrade policy)

## Changelog (v1 → v2)

| Section | Change |
|---------|--------|
| Sandbox Downgrade Policy | DESTRUCTIVE no longer downgraded to ALLOW with sandbox — stays REQUIRE_APPROVAL. Sandbox confines damage to project dir, but project-internal data loss is still data loss. |
| Sandbox Downgrade Policy | CODE_GEN no longer downgraded to ALLOW — stays REQUIRE_APPROVAL. Inline code cannot be statically validated; sandbox cannot inspect intent. |
| Seatbelt profile | Added `/var/folders` read-write (macOS temp files) and `/private/tmp` read-write. Without these, npm/pip/compilers fail. |
| Seatbelt profile | Added `(allow process-fork)` and `(allow process-exec (literal "/usr/bin/sandbox-exec"))` for nested process spawning. |
| bubblewrap config | Changed `--bind /tmp /tmp` to `--tmpfs /tmp` (isolated tmpfs, prevents IPC via shared /tmp). |
| bubblewrap config | Added `--ro-bind /etc /etc` (DNS resolution, SSL certs needed for git/npm). |
| Shell interpreter override | Explicitly excludes `-c`/`-e`/`--eval` flags from file-argument downgrade. `bash -c "echo hi"` stays CODE_GEN, not WRITE_PROJECT. |
| Combined Security Flow | Flow diagram updated to show sandbox wrapping happens AFTER approval decision, not as part of it. |
| Test Adaptations | Added sandbox-aware test expectations. |
| Two-Layer Principle | Clarified: Application Layer decides *whether*; OS Layer decides *what's physically possible*. They are NOT redundant — both must work correctly on their own. |

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
| **OS Layer** | Sandbox (Seatbelt / Landlock / Windows) | Kernel-level capability restriction — process physically cannot do harm beyond its allowed scope |

**Key principle**: The two layers complement each other, not replace each other. Each layer must be correct **on its own**.

- Application Layer = **UX + authorization** — decides *whether* the user should be allowed to do something. Must work correctly even without a sandbox.
- OS Layer = **safety net** — ensures the process *physically cannot* exceed its allowed scope. Must provide meaningful confinement regardless of application-layer decisions.

**This means:**
- The OS sandbox does NOT change *whether* a command needs approval. Approval decisions are purely application-layer.
- The OS sandbox changes *how* an approved/allowed command is executed — wrapped in kernel-level confinement.
- When sandbox is unavailable, the application layer still makes the same correct decisions; commands just execute without kernel-level confinement.

**Why sandbox does NOT downgrade approvals:**

| Category | With sandbox | Without sandbox | Rationale |
|----------|-------------|-----------------|-----------|
| DESTRUCTIVE | REQUIRE_APPROVAL | REQUIRE_APPROVAL | Sandbox confines damage to project dir, but project-internal data loss is still data loss. User must explicitly authorize deletion. |
| CODE_GEN | REQUIRE_APPROVAL | REQUIRE_APPROVAL | Inline code cannot be statically validated. Sandbox limits blast radius but cannot inspect code intent. User must acknowledge risk. |
| WRITE_SYSTEM | REQUIRE_APPROVAL | REQUIRE_APPROVAL | System-wide impact. Sandbox may prevent writes outside allowed paths, but user should know system is being modified. |
| NETWORK_OUT | REQUIRE_APPROVAL | REQUIRE_APPROVAL | Data exfiltration risk. Sandbox can block network, but if user approves it, network is permitted. Approval = informed consent. |
| UNKNOWN | REQUIRE_APPROVAL | REQUIRE_APPROVAL | No registry entry = cannot reason about effect. |

The sandbox's role is **confinement**, not **authorization**. After the application layer decides to allow or approve a command, the sandbox ensures that command cannot exceed its allowed scope.

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

**The action policy is the same regardless of sandbox availability.** Sandbox only affects execution wrapping, not approval decisions.

| Effect Category | Action | Examples |
|-----------------|--------|----------|
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

**Explicit exclusion**: The following inline-eval flags are NOT downgraded, regardless of other arguments:

| Interpreter | Flag | Category | Action |
|-------------|------|----------|--------|
| bash, sh, zsh, fish, ksh, csh | `-c` | CODE_GEN | REQUIRE_APPROVAL |
| python, python3 | `-c` | CODE_GEN | REQUIRE_APPROVAL |
| node | `-e`, `--eval` | CODE_GEN | REQUIRE_APPROVAL |
| perl | `-e` | CODE_GEN | REQUIRE_APPROVAL |
| ruby | `-e` | CODE_GEN | REQUIRE_APPROVAL |
| php | `-r` | CODE_GEN | REQUIRE_APPROVAL |

This is handled in CommandPolicy via `_shell_interpreter_override()`:
1. If the interpreter has `-c`/`-e`/`--eval` flags → return `CODE_GEN` (no override)
2. If the interpreter has a non-flag argument that looks like a file path → return `WRITE_PROJECT`
3. Otherwise → return base category `ESCALATE` → DENY

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
- `_shell_interpreter_override()` — special case: bash/sh/zsh + file arg → WRITE_PROJECT (with `-c`/`-e` exclusion)

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
| `bash -c "echo hi"` | DENY | CODE_GEN → REQUIRE_APPROVAL |
| `sh -c "echo hi"` | DENY | CODE_GEN → REQUIRE_APPROVAL |
| `chmod +x script.sh` | REQUIRE_APPROVAL | DESTRUCTIVE → REQUIRE_APPROVAL (same action, different reason) |
| `git log \| head` | REQUIRE_APPROVAL | READ_ONLY → ALLOW |
| `pytest 2>&1 \| tee log` | REQUIRE_APPROVAL | WRITE_PROJECT → ALLOW |
| `curl url \| sh` | DENY | DENY (hard deny rule, same) |
| `pip install foo` | ALLOW | WRITE_PROJECT → ALLOW (same) |
| `npm install` | ALLOW | WRITE_PROJECT → ALLOW (same) |
| `ls` | ALLOW | READ_ONLY → ALLOW (same) |
| `git push` | ALLOW | NETWORK_OUT → REQUIRE_APPROVAL (new: was incorrectly ALLOW) |
| `git reset --hard` | ALLOW | DESTRUCTIVE → REQUIRE_APPROVAL (new: was incorrectly ALLOW) |
| `some_unknown_tool` | ALLOW | UNKNOWN → REQUIRE_APPROVAL (new: was incorrectly ALLOW) |

New test categories to add:
- `TestEffectClassification` — verify registry lookups
- `TestPipeChainClassification` — verify pipe chain effect aggregation
- `TestSubcommandOverrides` — verify git subcommand handling
- `TestShellInterpreterOverride` — verify bash script.sh allowance and bash -c exclusion
- `TestUnknownCommandHandling` — verify UNKNOWN → REQUIRE_APPROVAL
- `TestSandboxWrapping` — verify commands are wrapped when sandbox is available
- `TestSandboxUnavailable` — verify commands execute directly when sandbox is unavailable

## OS Sandbox Layer

### Design Principle: Confinement, Not Authorization

The sandbox's sole purpose is to **confine** an already-approved command to its allowed scope. It does not make authorization decisions — that's the application layer's job.

**What the sandbox does:**
- Prevent file writes outside project directories (READ_ONLY and WRITE_PROJECT commands)
- Prevent file reads of sensitive system paths (optional, stricter mode)
- Prevent network access (unless explicitly allowed for NETWORK_OUT commands)
- Prevent privilege escalation (no sudo/setuid inside sandbox)
- Prevent IPC (shared memory, unix sockets outside project)

**What the sandbox does NOT do:**
- Decide whether a command needs approval
- Downgrade REQUIRE_APPROVAL to ALLOW
- Replace the effect classification system

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

macOS ships with `sandbox-exec` which applies Seatbelt profiles to processes.

**Critical macOS-specific considerations:**
- `/var/folders/*` is where macOS stores temp files (comparable to Linux `/tmp`). npm, pip, compilers all write here. Must be read-write.
- `/private/tmp` is the real path behind `/tmp` symlink on macOS. Must be read-write.
- Process forking is needed for tools like `make`, `npm`, `pre-commit` that spawn child processes.
- `sandbox-exec` itself must be allowed to execute for nested sandbox scenarios.

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

        # macOS temp directories — REQUIRED for npm/pip/compilers
        # /var/folders is the real temp dir; /tmp symlinks to /private/tmp
        lines.append('(allow file-read* file-write* (subpath "/var/folders"))')
        lines.append('(allow file-read* file-write* (subpath "/private/tmp"))')

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

        # Allow process forking (needed by make, npm, pre-commit, etc.)
        lines.append('(allow process-fork)')

        # Network
        if allow_network:
            lines.append('(allow network*)')
        else:
            lines.append('(deny network*)')

        # Allow signal, sysctl for normal process operation
        lines.append('(allow signal)')
        lines.append('(allow sysctl-read)')

        # Allow /etc for DNS resolution and SSL certs (needed by git, npm, pip)
        lines.append('(allow file-read* (subpath "/etc"))')

        return '\n'.join(lines)
```

#### Linux: Landlock + bubblewrap

Linux uses two complementary mechanisms:

- **Landlock LSM**: Filesystem access control (kernel >= 5.13)
- **bubblewrap (bwrap)**: Lightweight namespace isolation (user namespaces, no Docker needed)
- **seccomp-bpf**: System call filtering (optional, for additional hardening)

**Critical Linux-specific considerations:**
- `/etc` is needed read-only for DNS resolution, SSL certs, and nsswitch (git/npm/pip need this).
- `/tmp` should use `--tmpfs` (isolated tmpfs) rather than `--bind /tmp /tmp` to prevent IPC attacks via shared /tmp.
- `/home` may need read-only access for user config files (`.npmrc`, `.gitconfig`, etc.).
- `--unshare-all` unshares all namespaces including IPC namespace, which is the default secure position.

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
            allow_ipc=allow_ipc,
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
            allow_ipc=allow_ipc,
            cwd=cwd,
        )
        args_str = " ".join(shlex.quote(a) for a in bwrap_args)
        return f"bwrap {args_str} -- {command}"

    def _build_bwrap_args(self, allowed_paths, read_only_paths,
                          allow_network, allow_ipc, cwd) -> list[str]:
        args = [
            "--unshare-all",           # Unshare all namespaces (IPC, net, pid, user, uts, cgroup)
            "--die-with-parent",       # Kill sandbox when parent dies
        ]

        if not allow_network:
            # --unshare-all already unshares net, but be explicit
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

        # /etc read-only (DNS resolution, SSL certs, nsswitch — needed by git/npm/pip)
        if os.path.exists("/etc"):
            args.extend(["--ro-bind", "/etc", "/etc"])

        # /home read-only for user config files (.npmrc, .gitconfig, etc.)
        if os.path.exists("/home"):
            args.extend(["--ro-bind", "/home", "/home"])

        # /proc and /dev needed for basic operation
        args.extend(["--proc", "/proc"])
        args.extend(["--dev", "/dev"])

        # /tmp as isolated tmpfs (NOT --bind /tmp /tmp, which shares host /tmp)
        args.extend(["--tmpfs", "/tmp"])

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

### Sandbox and Application Layer Interaction

The sandbox does NOT change approval decisions. It only affects execution wrapping.

| Scenario | Application Layer Decision | Sandbox Wrapping | Final Execution |
|----------|---------------------------|-----------------|-----------------|
| `ls` (READ_ONLY, no sandbox) | ALLOW | None (sandbox unavailable) | Direct execution |
| `ls` (READ_ONLY, with sandbox) | ALLOW | sandbox.wrap_command() | Sandboxed execution |
| `rm build/` (DESTRUCTIVE, no sandbox) | REQUIRE_APPROVAL | None | User approves → direct execution |
| `rm build/` (DESTRUCTIVE, with sandbox) | REQUIRE_APPROVAL | sandbox.wrap_command() | User approves → sandboxed execution |
| `curl url` (NETWORK_OUT, with sandbox) | REQUIRE_APPROVAL | sandbox.wrap_command(allow_network=True) | User approves → sandboxed execution with network |
| `git log \| head` (READ_ONLY, with sandbox) | ALLOW | sandbox.wrap_shell_command() | Sandboxed execution |

**Key insight**: The sandbox is always applied when available, regardless of ALLOW vs REQUIRE_APPROVAL. Even ALLOW commands benefit from sandbox confinement (defense in depth).

### Combined Security Flow

```
Command Input
  │
  ├─ 1. Hard deny check (rm -rf /, curl | sh, sudo) → DENY (return immediately)
  │
  ├─ 2. Effect classification → effect_category
  │     ├─ Registry lookup (with subcommand/flag overrides)
  │     └─ Pipe chain aggregation (if shell mode)
  │
  ├─ 3. Determine action from effect_category
  │     ├─ READ_ONLY → ALLOW
  │     ├─ WRITE_PROJECT → ALLOW
  │     ├─ WRITE_SYSTEM → REQUIRE_APPROVAL
  │     ├─ DESTRUCTIVE → REQUIRE_APPROVAL
  │     ├─ ESCALATE → DENY
  │     ├─ NETWORK_OUT → REQUIRE_APPROVAL
  │     ├─ CODE_GEN → REQUIRE_APPROVAL
  │     └─ UNKNOWN → REQUIRE_APPROVAL
  │
  ├─ 4. If DENY → return DENY (no execution)
  │
  ├─ 5. If REQUIRE_APPROVAL → return approval request (wait for user)
  │     └─ User approves → proceed to step 6
  │     └─ User denies → return DENY
  │
  ├─ 6. If ALLOW or user-approved → prepare execution
  │     ├─ Determine sandbox params from effect_category:
  │     │   ├─ allow_network = (effect_category == NETWORK_OUT)
  │     │   └─ allow_ipc = False (always, unless explicitly needed in future)
  │     │
  │     ├─ Sandbox available?
  │     │   ├─ YES → wrap command with sandbox.wrap_command/wrap_shell_command()
  │     │   └─ NO  → execute directly (no wrapping)
  │     │
  │     └─ Execute (sandboxed or bare)
  │
  └─ Return result
```

### Updated File Structure

```
backend/app/security/
├── effect_category.py          # NEW: EffectCategory enum + danger level ordering + action policy mapping
├── command_effect_registry.py  # NEW: CommandEffectEntry + CommandEffectRegistry + default registrations
├── command_policy.py           # MODIFIED: Query registry, no sandbox-dependent approval logic
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

`ShellTool` needs minor changes to use sandbox wrapping. **The policy engine does NOT receive the sandbox** — approval decisions are sandbox-independent.

```python
class ShellTool(BaseTool):
    def __init__(self, security, path_security, sandbox=None):
        self.security = security
        self.path_security = path_security
        self.sandbox = sandbox or NullSandbox()
        # Policy does NOT receive sandbox — approval decisions are sandbox-independent
        self.policy = CommandPolicy(security, path_security)

    async def _execute_argv(self, argv, cwd, timeout, effect_category=None):
        # Wrap command in sandbox if available (confinement, not authorization)
        if self.sandbox.is_available():
            allow_network = (effect_category == EffectCategory.NETWORK_OUT)
            argv = self.sandbox.wrap_command(
                argv,
                cwd=cwd,
                allowed_paths=self.path_security.allowed_base_paths,
                read_only_paths=["/usr", "/bin", "/sbin", "/lib"],
                allow_network=allow_network,
            )
        # ... rest of execution unchanged

    async def _execute_shell(self, command, cwd, timeout, effect_category=None):
        # Wrap shell command in sandbox if available (confinement, not authorization)
        if self.sandbox.is_available():
            allow_network = (effect_category == EffectCategory.NETWORK_OUT)
            command = self.sandbox.wrap_shell_command(
                command,
                cwd=cwd,
                allowed_paths=self.path_security.allowed_base_paths,
                read_only_paths=["/usr", "/bin", "/sbin", "/lib"],
                allow_network=allow_network,
            )
        # ... rest of execution unchanged
```

`allow_network` is derived from the command's effect classification:
- `NETWORK_OUT` commands approved by user → `allow_network=True`
- All other commands → `allow_network=False`

The `effect_category` is passed from the `CommandDecision` to `_execute_decision()`, which forwards it to `_execute_argv()` or `_execute_shell()`. This is a read-only informational field — the policy engine has already made its decision.
