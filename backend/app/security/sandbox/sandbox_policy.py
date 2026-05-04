from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SandboxLevel(str, Enum):
    """Cross-platform sandbox strictness level.

    Inherits ``str`` so SandboxLevel("dev") works from string values.
    """

    STRICT = "strict"           # Minimal: system reads + project writes + limited exec
    DEV = "dev"                 # Development default: /Users rw, any exec, IPC/mach
    PERMISSIVE = "permissive"   # Debugging: nearly everything allowed, sandbox boundary kept


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
        """Derive a concrete policy from a SandboxLevel + caller overrides.

        Parameters
        ----------
        level:
            The strictness level. STRICT disables user paths, IPC, mach,
            and unrestricted process execution. DEV and PERMISSIVE enable them.
        allow_network:
            If True, allow outbound network connections.
        allowed_paths:
            Directories the sandboxed process may read and write.
        read_only_paths:
            Directories the sandboxed process may only read.
        """
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
