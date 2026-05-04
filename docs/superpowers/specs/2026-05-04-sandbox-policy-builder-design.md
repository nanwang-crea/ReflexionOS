# Sandbox Policy & Profile Builder Design

Date: 2026-05-04

## Problem

The current sandbox profile generation in ReflexionOS has several limitations:

1. **No formal policy abstraction** — `build_seatbelt_profile()` uses a `level: str` parameter with no type safety, and `LandlockSandbox._build_bwrap_args()` ignores levels entirely.
2. **Dead `allow_ipc` parameter** — declared in `SandboxProvider` ABC but never forwarded or implemented by any provider.
3. **No cross-platform policy sharing** — Seatbelt and Landlock each hardcode their own permission logic independently, with no shared concept of "strictness."
4. **Hardcoded `read_only_paths` at call site** — `shell_tool.py` passes `["/usr", "/bin", "/sbin", "/lib"]` directly, duplicating knowledge that belongs in the policy layer.
5. **No extensibility** — adding a new sandbox level or platform requires touching multiple unrelated files.

## Design

### Architecture

```
SandboxLevel (enum)            ← Cross-platform strictness enum
SandboxPolicy (dataclass)      ← Level + user params → concrete policy params
ProfileBuilder (ABC)           ← Abstract builder base class
  ├── SeatbeltProfileBuilder   ← macOS: generates .sb profile string
  └── LandlockProfileBuilder   ← Linux: generates bwrap args list
SandboxProvider (existing ABC) ← Now takes SandboxLevel in constructor
  ├── SeatbeltSandbox          ← Uses SeatbeltProfileBuilder internally
  └── LandlockSandbox          ← Uses LandlockProfileBuilder internally
```

### SandboxLevel Enum

```python
from enum import Enum

class SandboxLevel(str, Enum):
    STRICT = "strict"           # Minimal: system reads + project writes + limited exec
    DEV = "dev"                 # Development default: /Users rw, any exec, IPC/mach
    PERMISSIVE = "permissive"   # Debugging: nearly everything allowed, sandbox boundary kept
```

Inherits `str` for backward compatibility with existing `level="dev"` string values.

### SandboxPolicy Dataclass

```python
@dataclass
class SandboxPolicy:
    """Concrete sandbox parameters derived from SandboxLevel + overrides.

    Builders read only this dataclass — they never interpret SandboxLevel directly.
    """
    # Process
    allow_process_exec_all: bool = False  # True = unrestricted process-exec; False = system paths only
    allow_ipc: bool = False
    allow_mach: bool = False              # macOS-specific (bwrap ignores)

    # Filesystem
    allow_user_read: bool = False
    allow_user_write: bool = False
    allow_user_exec: bool = False

    # Network
    allow_network: bool = False

    # Paths
    allowed_paths: list[str] = field(default_factory=list)
    read_only_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_level(
        cls,
        level: SandboxLevel = SandboxLevel.DEV,
        *,
        allow_network: bool = False,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
    ) -> SandboxPolicy:
        strict = level == SandboxLevel.STRICT
        return cls(
            allow_process_exec_all=not strict,
            allow_ipc=not strict,
            allow_mach=not strict,
            allow_user_read=not strict,
            allow_user_write=not strict,    # DEV + PERMISSIVE both allow /Users write
            allow_user_exec=not strict,
            allow_network=allow_network,
            allowed_paths=allowed_paths or [],
            read_only_paths=read_only_paths or [],
        )
```

### ProfileBuilder ABC

```python
from abc import ABC, abstractmethod

class ProfileBuilder(ABC):
    """Cross-platform sandbox profile builder base class."""

    def __init__(self, policy: SandboxPolicy):
        self.policy = policy

    @abstractmethod
    def build(self) -> str | list[str]:
        """Build platform-specific sandbox configuration.

        Returns:
            str for Seatbelt (.sb profile),
            list[str] for Landlock/bwrap (argument list).
        """
        ...
```

### SeatbeltProfileBuilder

```python
class SeatbeltProfileBuilder(ProfileBuilder):
    def __init__(self, policy: SandboxPolicy):
        super().__init__(policy)
        self.lines: list[str] = []

    def build(self) -> str:
        self._header()
        self._system()
        self._temp()
        self._user()
        self._paths()
        self._process()
        self._ipc()
        self._network()
        self._misc()
        return "\n".join(self.lines)

    # Template methods — each appends to self.lines based on self.policy
```

Template method responsibilities:

| Method | Policy fields used | Seatbelt rules |
|--------|-------------------|----------------|
| `_header` | — | `(version 1)`, `(deny default)` |
| `_system` | — | Read-only for `/usr`, `/bin`, `/sbin`, `/lib`, `/System`, `/dev`, `/etc` + `file-map-executable` |
| `_temp` | — | Read-write for `/tmp`, `/private/tmp`, `/var/folders` |
| `_user` | `allow_user_read`, `allow_user_write`, `allow_user_exec` | `/Users` subpath permissions |
| `_paths` | `allowed_paths`, `read_only_paths` | Project-specific read-write and read-only |
| `_process` | `allow_process_exec_all` | `process-exec` (all or system-only) + `process-fork` + `process-info*` |
| `_ipc` | `allow_ipc`, `allow_mach` | `ipc*` and `mach*` (macOS-specific, critical for git) |
| `_network` | `allow_network` | `network*` allow/deny |
| `_misc` | — | `signal`, `sysctl-read` |

### LandlockProfileBuilder

```python
class LandlockProfileBuilder(ProfileBuilder):
    def __init__(self, policy: SandboxPolicy):
        super().__init__(policy)
        self.args: list[str] = []

    def build(self) -> list[str]:
        self._base()
        self._network()
        self._binds()
        self._virtual_fs()
        self._chdir()
        return self.args
```

Template method responsibilities:

| Method | Policy fields used | bwrap rules |
|--------|-------------------|-------------|
| `_base` | — | `--unshare-all`, `--die-with-parent` |
| `_network` | `allow_network` | `--unshare-net` when denied |
| `_binds` | `allowed_paths`, `read_only_paths`, `allow_user_read`, `allow_user_write` | `--bind`/`--ro-bind` for system and user paths |
| `_virtual_fs` | — | `--proc /proc`, `--dev /dev`, `--tmpfs /tmp` |
| `_chdir` | — | `--chdir <cwd>` (cwd passed separately) |

Note: `allow_mach` is macOS-specific and ignored by Landlock. `allow_ipc` maps to whether `--unshare-ipc` is included in `--unshare-all` overrides.

### SandboxProvider Integration

`SandboxProvider` ABC remains unchanged. Concrete providers gain a `level` constructor parameter:

```python
class SeatbeltSandbox(SandboxProvider):
    def __init__(self, level: SandboxLevel = SandboxLevel.DEV):
        self.level = level

    def wrap_command(self, argv, *, cwd, allowed_paths, read_only_paths,
                     allow_network, allow_ipc):
        policy = SandboxPolicy.from_level(
            self.level,
            allow_network=allow_network,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
        )
        profile = SeatbeltProfileBuilder(policy).build()
        return ["/usr/bin/sandbox-exec", "-p", profile, "--"] + list(argv)
```

`LandlockSandbox` follows the same pattern. The `allow_ipc` per-call parameter is **not** forwarded to `SandboxPolicy.from_level()` — IPC permission is derived from `SandboxLevel` alone. The per-call `allow_ipc` parameter remains in the ABC for future use but is currently unused at the provider level (same as today, just now documented).

### Factory

```python
def create_sandbox(level: SandboxLevel = SandboxLevel.DEV) -> SandboxProvider:
    for cls in (SeatbeltSandbox, LandlockSandbox):
        provider = cls(level=level)
        if provider.is_available():
            return provider
    return NullSandbox()
```

### ShellTool Changes

- Remove hardcoded `read_only_paths=["/usr", "/bin", "/sbin", "/lib"]` from call sites
- System read-only paths (`/usr`, `/bin`, `/sbin`, `/lib`, `/System`, `/dev`, `/etc`) are now derived **inside each Builder** based on `SandboxLevel`, not passed by the caller
- `SandboxProvider` ABC signature keeps `read_only_paths` for caller-specified extra paths, but `ShellTool` will pass `None` (the default)
- Call site simplifies to only passing `allowed_paths` and `allow_network`

### System Paths Ownership

System paths (always read-only) are the Builder's responsibility, not the caller's:

| Platform | Paths always read-only | Source |
|----------|----------------------|--------|
| macOS (Seatbelt) | `/usr`, `/bin`, `/sbin`, `/lib`, `/System`, `/dev`, `/etc` | `_system()` template method |
| Linux (bwrap) | `/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/etc`, `/home` | `_binds()` template method |

Callers only specify:
- `allowed_paths`: project directories that need read-write access
- `read_only_paths`: additional caller-specific read-only directories (optional, typically `None`)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `sandbox_policy.py` | **NEW** | `SandboxLevel` enum + `SandboxPolicy` dataclass |
| `profile_builder.py` | **NEW** | `ProfileBuilder` ABC |
| `seatbelt_profile.py` | **REWRITE** | Replace `build_seatbelt_profile()` function with `SeatbeltProfileBuilder` class. Delete the old function entirely. |
| `landlock_profile.py` | **NEW** | `LandlockProfileBuilder` class |
| `seatbelt.py` | **MODIFY** | Add `level` param; use `SeatbeltProfileBuilder` instead of deleted function |
| `landlock.py` | **MODIFY** | Add `level` param; use `LandlockProfileBuilder` instead of `_build_bwrap_args` |
| `factory.py` | **MODIFY** | `create_sandbox(level=)` param |
| `__init__.py` | **MODIFY** | Export new symbols |
| `shell_tool.py` | **MODIFY** | Remove hardcoded `read_only_paths`; pass only `allowed_paths` + `allow_network` |

## Backward Compatibility

- `SandboxLevel(str, Enum)` ensures `SandboxLevel("dev")` works from string
- `create_sandbox()` defaults to `SandboxLevel.DEV` — no breaking change for callers that don't pass a level
- `build_seatbelt_profile()` is **deleted** — all callers must migrate to `SeatbeltProfileBuilder`
- `SandboxProvider.wrap_command()` signature unchanged — level is constructor-injected, not per-call

## Open Questions

1. **`allow_ipc` per-call override**: The `SandboxProvider` ABC accepts `allow_ipc: bool` per call. With the new design, IPC is derived from `SandboxLevel`. **Decision: level takes precedence; per-call `allow_ipc` is not forwarded to policy. The parameter remains in the ABC signature for future use.**

2. **`cwd` in LandlockPolicyBuilder**: The current `_build_bwrap_args` takes `cwd` for `--chdir`. `ProfileBuilder.__init__` only takes `policy`. Options: (a) add `cwd` to `LandlockProfileBuilder.__init__`, (b) add `cwd` to `SandboxPolicy`, (c) pass `cwd` to `build()`. **Decision: (a) add `cwd` to `LandlockProfileBuilder.__init__`** — cwd is not a policy concern, it's an execution concern.

## Testing

- Unit tests for `SandboxPolicy.from_level()` verifying each level's derived flags
- Unit tests for `SeatbeltProfileBuilder` at each level (snapshot of expected output)
- Unit tests for `LandlockProfileBuilder` at each level
- Integration test verifying `SeatbeltSandbox.wrap_command()` produces correct profile
- Integration test verifying `create_sandbox(level=SandboxLevel.STRICT)` propagates level correctly
