"""
沙盒提供者抽象基类。

定义所有操作系统级沙盒后端（Linux Landlock、macOS Seatbelt 等）必须实现的
统一接口：探测当前环境是否可用（is_available）、把一条命令“包裹”成受限执行
的命令（wrap_command/wrap_shell_command）。不同平台的沙盒机制原理不同——
Landlock 是内核层的文件系统访问控制（LSM），Seatbelt 是 macOS 的
沙盒 profile 机制（sandbox-exec 配置文件）——但对上层调用者暴露的行为一致：
传入原始命令和路径/网络限制，拿到一个可以直接执行、且已被沙盒约束的新命令。
"""

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
    """沙盒提供者抽象基类，子类对应具体平台的沙盒实现（如 Landlock、Seatbelt）。"""

    @abstractmethod
    def is_available(self) -> bool:
        """
        函数名：is_available
        入参：无
        功能：探测当前运行环境是否支持并可以使用本沙盒后端。
        运行逻辑：由子类实现，通常检查内核版本/系统调用可用性（如 Landlock
            需要较新的 Linux 内核）或可执行工具是否存在（如 Seatbelt 需要
            系统自带的 sandbox-exec）。
        出参：bool - True 表示本沙盒后端在当前主机上可用，False 表示不可用
            （调用方应退化为不加沙盒或使用其他后端）。
        """
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
        """
        函数名：wrap_command
        入参：
            - argv (list[str]): 原始命令及其参数列表（如 ["python", "script.py"]）
            - cwd (str): 命令执行时的工作目录
            - allowed_paths (list[str] | None): 允许读写的路径列表，为 None 时按
              子类默认策略处理
            - read_only_paths (list[str] | None): 仅允许只读访问的路径列表
            - allow_network (bool): 是否允许发起网络访问
            - allow_ipc (bool): 是否允许进程间通信（如 Unix 域套接字、共享内存）
        功能：将一条 argv 形式的命令包裹为在沙盒内执行的新命令。
        运行逻辑：由子类实现，具体做法是在原始 argv 前面拼接沙盒可执行文件及其
            策略参数（例如 Landlock 通过预加载或子进程施加内核级文件访问限制，
            Seatbelt 通过 sandbox-exec 加载生成好的沙盒 profile）。
        出参：list[str] - 新的 argv，直接执行即可在沙盒约束下启动原始命令。
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
        """
        函数名：wrap_shell_command
        入参：
            - command (str): 原始 shell 命令字符串（将通过 `sh -c` 执行）
            - cwd (str): 命令执行时的工作目录
            - allowed_paths (list[str] | None): 允许读写的路径列表
            - read_only_paths (list[str] | None): 仅允许只读访问的路径列表
            - allow_network (bool): 是否允许发起网络访问
            - allow_ipc (bool): 是否允许进程间通信
        功能：将一条 shell 命令字符串包裹为在沙盒内执行的新命令字符串。
        运行逻辑：与 wrap_command 类似，但操作对象是完整的 shell 命令字符串
            而非 argv 列表，由子类拼接对应的沙盒调用前缀。
        出参：str - 新的 shell 命令字符串，通过 `sh -c` 执行即可在沙盒约束下
            启动原始命令。
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

        Returns:
            SandboxRunResult | None: 命令执行结果（成功标志/输出/错误/返回码）；
                基类默认返回 None，表示“本后端不直接支持一步执行并取结果”，
                调用方需改用 wrap_command/wrap_shell_command 自行拼接后再执行。
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

        Returns:
            SandboxRunResult | None: 命令执行结果；基类默认返回 None，
                含义与 run_command 一致——本后端不直接支持一步执行取结果。
        """
        return None
