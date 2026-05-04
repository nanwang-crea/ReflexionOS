from __future__ import annotations

from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxPolicy


class SeatbeltProfileBuilder(ProfileBuilder):
    """macOS Seatbelt profile for Agent Shell (pragmatic mode).

    Philosophy:
    - Do NOT fight the OS (allow default)
    - Only restrict high-risk capabilities:
        - network
        - sensitive file paths
        - system write
    """

    def __init__(self, policy: SandboxPolicy) -> None:
        super().__init__(policy)
        self.lines: list[str] = []

    def build(self) -> str:
        self._header()
        self._temp()
        self._paths()
        self._network()
        self._process()
        self._misc()
        return "\n".join(self.lines)

    # ---------------- core ----------------

    def _header(self) -> None:
        self.lines.append("(version 1)")
        # ✅ Agent shell 模式核心：默认允许
        self.lines.append("(allow default)")

    # ---------------- filesystem ----------------

    def _temp(self) -> None:
        """Ensure temp dirs are writable (some tools rely on this)."""
        for p in ("/tmp", "/private/tmp", "/var/folders"):
            self.lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

    def _paths(self) -> None:
        """Restrict only dangerous paths (deny-based model)."""

        # 🔴 禁止写系统目录（防破坏）
        self.lines.append('(deny file-write* (subpath "/System"))')
        self.lines.append('(deny file-write* (subpath "/usr"))')

        # 🔴 禁止读取敏感信息
        self.lines.append('(deny file-read* (subpath "/Users/*/.ssh"))')
        self.lines.append('(deny file-read* (subpath "/Users/*/.gnupg"))')

        # 可选：项目路径显式允许（增强可控性）
        for p in self.policy.allowed_paths:
            self.lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

        for p in self.policy.read_only_paths:
            self.lines.append(f'(allow file-read* (subpath "{p}"))')

    # ---------------- process ----------------

    def _process(self) -> None:
        """Do NOT restrict exec heavily (breaks ecosystem)."""
        self.lines.append("(allow process-exec)")
        self.lines.append("(allow process-fork)")

    # ---------------- network ----------------

    def _network(self) -> None:
        if self.policy.allow_network:
            self.lines.append("(allow network*)")
        else:
            # 🔴 核心隔离：禁止网络
            self.lines.append("(deny network*)")

    # ---------------- misc ----------------

    def _misc(self) -> None:
        self.lines.append("(allow signal)")
        self.lines.append("(allow sysctl-read)")