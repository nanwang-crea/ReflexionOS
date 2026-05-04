from __future__ import annotations

from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxPolicy


class SeatbeltProfileBuilder(ProfileBuilder):
    """macOS Seatbelt (sandbox-exec) profile builder.

    Generates a .sb profile string using the template method pattern.
    Each private method appends Seatbelt rules to ``self.lines`` based on
    the policy provided at construction time.
    """

    def __init__(self, policy: SandboxPolicy) -> None:
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

    # -- template methods ---------------------------------------------------

    def _header(self) -> None:
        self.lines.append("(version 1)")
        self.lines.append("(deny default)")

    def _system(self) -> None:
        """Read-only system binary/library paths (always needed)."""
        for prefix in ("/usr", "/bin", "/sbin", "/lib", "/System", "/dev", "/etc"):
            self.lines.append(f'(allow file-read* (subpath "{prefix}"))')
        # dyld / executable mapping — without this Python/git crash
        self.lines.append("(allow file-map-executable)")

    def _temp(self) -> None:
        """Temporary directories (always read-write)."""
        for p in ("/tmp", "/private/tmp", "/var/folders"):
            self.lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

    def _user(self) -> None:
        """User home directory — controlled by policy."""
        if self.policy.allow_user_read:
            self.lines.append('(allow file-read* (subpath "/Users"))')
        if self.policy.allow_user_write:
            self.lines.append('(allow file-write* (subpath "/Users"))')
        if self.policy.allow_user_exec:
            self.lines.append('(allow process-exec (subpath "/Users"))')

    def _paths(self) -> None:
        """Project-specific read-write and read-only paths."""
        for p in self.policy.allowed_paths:
            self.lines.append(f'(allow file-read* file-write* (subpath "{p}"))')
        for p in self.policy.read_only_paths:
            self.lines.append(f'(allow file-read* (subpath "{p}"))')

    def _process(self) -> None:
        """Process execution and forking."""
        if self.policy.allow_process_exec_all:
            # dev / permissive: must allow, otherwise venv / git / python break
            self.lines.append("(allow process-exec)")
        else:
            # strict: only system paths
            for prefix in ("/usr", "/bin", "/sbin"):
                self.lines.append(f'(allow process-exec (subpath "{prefix}"))')
        self.lines.append("(allow process-fork)")
        self.lines.append("(allow process-info*)")  # prevents some programs from aborting

    def _ipc(self) -> None:
        """Inter-process communication."""
        if self.policy.allow_ipc:
            self.lines.append("(allow ipc*)")
        if self.policy.allow_mach:
            # macOS core IPC — without this git SIGABRTs
            self.lines.append("(allow mach*)")

    def _network(self) -> None:
        """Network access."""
        if self.policy.allow_network:
            self.lines.append("(allow network*)")
        else:
            self.lines.append("(deny network*)")

    def _misc(self) -> None:
        """Miscellaneous always-needed permissions."""
        self.lines.append("(allow signal)")
        self.lines.append("(allow sysctl-read)")
