from __future__ import annotations

import os
from typing import ClassVar

from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxPolicy


class LandlockProfileBuilder(ProfileBuilder):
    """Linux bwrap profile builder (pragmatic mode).

    Philosophy (same as SeatbeltProfileBuilder):
    - Do NOT fight the OS — bind ``/`` as writable by default
    - Only restrict high-risk capabilities:
        - network (via --unshare-net)
        - sensitive file paths (--ro-bind to deny write)
        - system write protection (--ro-bind for /usr, /System, etc.)
    """

    # Paths always mounted read-only to prevent system corruption
    _SYSTEM_RO_PATHS: ClassVar[tuple[str, ...]] = (
        "/usr", "/bin", "/sbin", "/lib", "/lib64",
    )

    # Sensitive paths always denied even in permissive mode
    _DENIED_PATHS: ClassVar[tuple[str, ...]] = (
        "/etc/shadow", "/etc/ssh", "/root/.ssh", "/root/.gnupg",
    )

    def __init__(self, policy: SandboxPolicy, *, cwd: str) -> None:
        super().__init__(policy)
        self.cwd = cwd
        self.args: list[str] = []

    def build(self) -> list[str]:
        self._base()
        self._network()
        self._binds()
        self._virtual_fs()
        self._chdir()
        return self.args

    # -- template methods ---------------------------------------------------

    def _base(self) -> None:
        """Base bwrap isolation — minimal, not aggressive."""
        self.args.append("--die-with-parent")

    def _network(self) -> None:
        """Restrict network when policy says so."""
        if not self.policy.allow_network:
            self.args.append("--unshare-net")

    def _binds(self) -> None:
        """Bind mounts — allow by default, restrict only dangerous paths."""

        # Bind entire root filesystem as writable (pragmatic: allow default)
        if os.path.isdir("/"):
            self.args.extend(["--bind", "/", "/"])

        # Override system paths as read-only (prevent system corruption)
        for prefix in self._SYSTEM_RO_PATHS:
            if os.path.isdir(prefix):
                self.args.extend(["--ro-bind", prefix, prefix])

        # Override sensitive paths as read-only
        for p in self._DENIED_PATHS:
            if os.path.exists(p):
                self.args.extend(["--ro-bind", p, p])

        # Explicit allowed paths (writable, for project directories)
        for p in self.policy.allowed_paths:
            self.args.extend(["--bind", p, p])

        # Read-only paths (caller-specified)
        for p in self.policy.read_only_paths:
            self.args.extend(["--ro-bind", p, p])

    def _virtual_fs(self) -> None:
        """Virtual filesystems."""
        self.args.extend(["--proc", "/proc"])
        self.args.extend(["--dev", "/dev"])
        self.args.extend(["--tmpfs", "/tmp"])

    def _chdir(self) -> None:
        """Working directory."""
        self.args.extend(["--chdir", self.cwd])
