from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys

from app.security.sandbox.base import SandboxProvider


class LandlockSandbox(SandboxProvider):
    """Sandbox provider for Linux using bubblewrap (bwrap)."""

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

    def _build_bwrap_args(
        self,
        *,
        cwd: str,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
    ) -> list[str]:
        allowed_paths = allowed_paths or []
        read_only_paths = read_only_paths or []

        args: list[str] = [
            "--unshare-all",
            "--die-with-parent",
        ]

        if not allow_network:
            args.append("--unshare-net")

        # Writable bind mounts for allowed paths
        for p in allowed_paths:
            args.extend(["--bind", p, p])

        # Read-only system paths
        for prefix in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/home"):
            if os.path.isdir(prefix):
                args.extend(["--ro-bind", prefix, prefix])

        # Read-only paths requested by caller
        for p in read_only_paths:
            args.extend(["--ro-bind", p, p])

        # Virtual filesystems
        args.extend(["--proc", "/proc"])
        args.extend(["--dev", "/dev"])
        args.extend(["--tmpfs", "/tmp"])

        # Working directory
        args.extend(["--chdir", cwd])

        return args

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
        bwrap_args = self._build_bwrap_args(
            cwd=cwd,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
        )
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
        bwrap_args = self._build_bwrap_args(
            cwd=cwd,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
            allow_network=allow_network,
        )
        args_str = " ".join(shlex.quote(a) for a in bwrap_args)
        return f"bwrap {args_str} -- {command}"
