from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.landlock_profile import LandlockProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxLevel, SandboxPolicy


class LandlockSandbox(SandboxProvider):
    """Sandbox provider for Linux using bubblewrap (bwrap)."""

    def __init__(self, level: SandboxLevel = SandboxLevel.DEV) -> None:
        self.level = level

    def is_available(self) -> bool:
        if sys.platform != "linux":
            return False
        if not shutil.which("bwrap"):
            return False
        return self._check_bwrap_support()

    def _check_bwrap_support(self) -> bool:
        """Verify bwrap actually works on this kernel."""
        try:
            result = subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", "--", "true"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def wrap_command(
        self,
        argv: list[str],
        *,
        cwd: str,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> list[str]:
        policy = SandboxPolicy.from_level(
            self.level,
            allow_network=allow_network,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
        )
        bwrap_args = LandlockProfileBuilder(policy, cwd=cwd).build()
        return ["bwrap"] + bwrap_args + ["--"] + list(argv)

    def wrap_shell_command(
        self,
        command: str,
        *,
        cwd: str,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> str:
        policy = SandboxPolicy.from_level(
            self.level,
            allow_network=allow_network,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
        )
        bwrap_args = LandlockProfileBuilder(policy, cwd=cwd).build()
        args_str = " ".join(shlex.quote(a) for a in bwrap_args)
        return f"bwrap {args_str} -- {command}"
