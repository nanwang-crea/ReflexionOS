from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SandboxRunResult:
    """沙盒直接执行命令的结果（与 subprocess.run 返回值对齐）。"""
    success: bool
    output: str
    error: str | None
    return_code: int


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

    def run_command(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int = 300,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """直接执行 argv 命令并返回结果。默认为 None（seatbelt/landlock 不覆盖）。

        Args:
            argv: 命令参数列表
            cwd: 工作目录
            timeout: 超时秒数（传给底层执行机制，如 proc.communicate）
            allowed_paths: 允许写入的路径
            read_only_paths: 只读路径
            allow_network: 是否允许网络
            allow_ipc: 是否允许 IPC
        """
        return None

    def run_shell_command(
        self,
        command: str,
        *,
        cwd: str,
        timeout: int = 300,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
        allow_network: bool = False,
        allow_ipc: bool = False,
    ) -> SandboxRunResult | None:
        """直接执行 shell 命令并返回结果。默认为 None。

        Args:
            command: shell 命令字符串
            cwd: 工作目录
            timeout: 超时秒数
            allowed_paths: 允许写入的路径
            read_only_paths: 只读路径
            allow_network: 是否允许网络
            allow_ipc: 是否允许 IPC
        """
        return None
