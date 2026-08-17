"""
沙盒工厂模块。

按平台自动选择可用的沙盒后端：Windows 使用 WindowsSandbox，macOS 使用
Seatbelt（sandbox-exec），Linux 使用 Landlock（内核 LSM，通过 bwrap 等
方式施加文件系统访问限制）。若当前主机三者都不可用（如内核版本过低、
缺少必要工具），则退化为 NullSandbox——不做任何隔离，直接透传原始命令，
保证上层调用逻辑无需区分“有沙盒/无沙盒”两种路径。
"""

from __future__ import annotations

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.landlock import LandlockSandbox
from app.security.sandbox.sandbox_policy import SandboxLevel
from app.security.sandbox.seatbelt import SeatbeltSandbox
from app.security.sandbox.windows import WindowsSandbox


class NullSandbox(SandboxProvider):
    """
    空沙盒实现：原样透传命令，不做任何隔离限制。

    用于当前主机上没有任何真实沙盒后端可用时的兜底。is_available 始终
    返回 False，因此 create_sandbox 的选择逻辑永远不会主动选中它作为
    “生效中的沙盒”；但调用方仍可以安全地调用它的 wrap 方法（相当于
    no-op），无需为“没有沙盒”这种情况单独写分支。
    """

    def is_available(self) -> bool:
        """
        函数名：is_available
        入参：无
        功能：声明本沙盒后端是否可用。
        运行逻辑：空沙盒不提供任何真实隔离能力，恒定返回 False，使得
            create_sandbox 的遍历逻辑永远不会把它当作“找到的可用后端”。
        出参：bool - 始终为 False。
        """
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
        """
        函数名：wrap_command
        入参：见基类 SandboxProvider.wrap_command（cwd/路径/网络/IPC 等
            限制参数在空沙盒实现中均被忽略，不施加任何约束）
        功能：不做任何包裹，原样返回命令。
        运行逻辑：直接复制 argv 列表并返回，不拼接任何沙盒可执行文件或
            策略参数。
        出参：list[str] - 与传入 argv 内容相同的新列表（浅拷贝）。
        """
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
        """
        函数名：wrap_shell_command
        入参：见基类 SandboxProvider.wrap_shell_command（各类限制参数
            在空沙盒实现中均被忽略）
        功能：不做任何包裹，原样返回 shell 命令字符串。
        运行逻辑：直接返回传入的 command，不做任何修改。
        出参：str - 与传入 command 相同的字符串。
        """
        return command


def create_sandbox(level: SandboxLevel = SandboxLevel.DEV) -> SandboxProvider:
    """
    函数名：create_sandbox
    入参：
        - level (SandboxLevel): 沙盒严格程度级别，默认 SandboxLevel.DEV。
          会传给被选中的具体 Provider 构造函数，用于推导对应的访问策略
          （如允许哪些路径、是否允许网络等）。
    功能：按平台优先级依次探测并返回第一个可用的沙盒后端实例。
    运行逻辑：
        1. 依次尝试实例化 WindowsSandbox（仅 win32 生效）、SeatbeltSandbox
           （仅 macOS 生效）、LandlockSandbox（仅 Linux 生效），并调用其
           is_available() 探测当前主机是否真正支持。
        2. 命中第一个 is_available() 返回 True 的实例即直接返回，不再
           继续尝试后续候选。
        3. 若三者都不可用（探测均为 False），返回 NullSandbox 实例作为
           兜底，保证调用方始终能拿到一个可用的 SandboxProvider。
    出参：SandboxProvider - 选中的具体沙盒实现，或兜底的 NullSandbox。
    """
    for cls in (WindowsSandbox, SeatbeltSandbox, LandlockSandbox):
        provider = cls(level=level)
        if provider.is_available():
            return provider
    return NullSandbox()
