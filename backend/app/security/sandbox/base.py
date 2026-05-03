from abc import ABC, abstractmethod


class SandboxProvider(ABC):
    """Abstract base class for OS-level sandbox providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this sandbox backend is usable on the current host."""
        ...

    @abstractmethod
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
        """Wrap an argv list so it runs inside the sandbox.

        Returns a new argv that, when executed, launches the original command
        inside the sandbox with the given filesystem / network constraints.
        """
        ...

    @abstractmethod
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
        """Wrap a shell command string so it runs inside the sandbox.

        Returns a shell command string that, when executed via ``sh -c``,
        launches the original command inside the sandbox.
        """
        ...
