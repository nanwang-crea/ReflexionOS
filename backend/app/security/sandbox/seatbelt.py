from __future__ import annotations

import os
import shlex
import sys

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.seatbelt_profile import build_seatbelt_profile


class SeatbeltSandbox(SandboxProvider):
    """Sandbox provider for macOS using the Seatbelt sandbox-exec mechanism."""

    def is_available(self) -> bool:
        return sys.platform == "darwin" and os.path.exists("/usr/bin/sandbox-exec")

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
        profile = build_seatbelt_profile(
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
        )
        return ["/usr/bin/sandbox-exec", "-p", profile, "--"] + list(argv)

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
        profile = build_seatbelt_profile(
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
        )
        return f"/usr/bin/sandbox-exec -p {shlex.quote(profile)} -- {command}"
