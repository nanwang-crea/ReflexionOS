from __future__ import annotations

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.landlock import LandlockSandbox
from app.security.sandbox.seatbelt import SeatbeltSandbox


class NullSandbox(SandboxProvider):
    """A no-op sandbox that passes commands through unchanged.

    Used as a fallback when no real sandbox backend is available on the host.
    ``is_available`` always returns False so the factory never selects it
    as an active provider, but callers can still use the wrap methods safely.
    """

    def is_available(self) -> bool:
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
        return list(argv)

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
        return command


def create_sandbox() -> SandboxProvider:
    """Return the first available sandbox provider, or NullSandbox.

    Tries Seatbelt (macOS) first, then Landlock/bwrap (Linux).
    If neither is available, returns a NullSandbox that passes
    commands through unchanged.
    """
    for cls in (SeatbeltSandbox, LandlockSandbox):
        provider = cls()
        if provider.is_available():
            return provider
    return NullSandbox()
