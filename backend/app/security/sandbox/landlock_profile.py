from __future__ import annotations

import os
from typing import ClassVar

from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxPolicy


class LandlockProfileBuilder(ProfileBuilder):
    """Linux Landlock/bwrap profile builder.

    Generates a bwrap argument list using the template method pattern.
    Each private method appends bwrap flags to ``self.args`` based on
    the policy provided at construction time.
    """

    # System paths always mounted read-only (if they exist)
    _SYSTEM_RO_PATHS: ClassVar[tuple[str, ...]] = (
        "/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc",
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
        """Base bwrap isolation flags."""
        self.args.append("--unshare-all")
        self.args.append("--die-with-parent")

    def _network(self) -> None:
        """Network namespace sharing."""
        if not self.policy.allow_network:
            self.args.append("--unshare-net")

    def _binds(self) -> None:
        """Bind mounts for system, user, and project paths."""

        # System paths — always read-only
        for prefix in self._SYSTEM_RO_PATHS:
            if os.path.isdir(prefix):
                self.args.extend(["--ro-bind", prefix, prefix])

        # User home directories — controlled by policy
        if os.path.isdir("/home"):
            if self.policy.allow_user_read and self.policy.allow_user_write:
                self.args.extend(["--bind", "/home", "/home"])
            elif self.policy.allow_user_read:
                self.args.extend(["--ro-bind", "/home", "/home"])

        # Writable bind mounts for allowed paths
        for p in self.policy.allowed_paths:
            self.args.extend(["--bind", p, p])

        # Read-only bind mounts for caller-specified paths
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
