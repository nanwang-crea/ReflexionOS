"""
macOS 平台沙盒实现（基于 Seatbelt / sandbox-exec）。

Seatbelt 是 macOS 系统自带的沙盒机制，通过系统工具 `sandbox-exec` 加载
一段 Scheme 风格的 `.sb` 策略文本（profile），由内核在进程执行期间按
该策略拦截文件访问、网络访问等系统调用。命令被 wrap 后，实际执行的是
`sandbox-exec -p <profile> -- <原始命令>`：sandbox-exec 先解析并注册
沙盒策略，再 exec 原始命令，使其自出生起就处于受限状态。
"""

from __future__ import annotations

import os
import shlex
import sys

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.sandbox_policy import SandboxLevel, SandboxPolicy
from app.security.sandbox.seatbelt_profile import SeatbeltProfileBuilder


class SeatbeltSandbox(SandboxProvider):
    """基于 macOS Seatbelt（sandbox-exec）机制的沙盒实现。"""

    def __init__(self, level: SandboxLevel = SandboxLevel.DEV) -> None:
        """
        函数名：__init__
        入参：
            - level (SandboxLevel): 沙盒严格程度级别，默认 SandboxLevel.DEV，
              后续 wrap_command/wrap_shell_command 会据此推导具体访问策略。
        功能：保存沙盒级别配置，供后续构建 Seatbelt profile 时使用。
        运行逻辑：仅做属性赋值，不涉及任何系统探测或副作用。
        出参：无。
        """
        self.level = level

    def is_available(self) -> bool:
        """
        函数名：is_available
        入参：无
        功能：探测当前主机是否具备使用 Seatbelt 沙盒的条件。
        运行逻辑：Seatbelt 是 macOS 专属机制，因此要求 sys.platform 为
            "darwin"，且系统自带的 /usr/bin/sandbox-exec 可执行文件
            确实存在（理论上 macOS 都会自带，此处仍做防御性检查）。
        出参：bool - True 表示当前主机可以使用 Seatbelt 沙盒，
            False 表示不可用。
        """
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
        """
        函数名：wrap_command
        入参：见基类 SandboxProvider.wrap_command——argv 为原始命令，
            cwd 为工作目录（Seatbelt profile 中不直接使用 cwd，工作
            目录仍由外层 subprocess 调用时的 cwd 参数控制），
            allowed_paths/read_only_paths 控制可写/只读路径范围，
            allow_network/allow_ipc 控制网络与 IPC 权限。
        功能：将原始 argv 命令包裹为一条完整的 sandbox-exec 命令。
        运行逻辑：
            1. 根据 level 与传入的路径/网络参数，通过 SandboxPolicy.from_level
               生成具体的沙盒策略对象。
            2. 用 SeatbeltProfileBuilder 将策略翻译为 `.sb` 格式的
               Seatbelt profile 文本。
            3. 拼接成最终 argv：["/usr/bin/sandbox-exec", "-p", profile,
               "--"] + 原始命令；"-p" 指定内联的策略文本，"--" 之后
               即为真正要在沙盒里执行的命令本身。
        出参：list[str] - 可直接传给 subprocess 执行的新 argv 列表。
        """
        policy = SandboxPolicy.from_level(
            self.level,
            allow_network=allow_network,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
        )
        profile = SeatbeltProfileBuilder(policy).build()
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
        """
        函数名：wrap_shell_command
        入参：见基类 SandboxProvider.wrap_shell_command——command 为原始
            shell 命令字符串，其余参数含义与 wrap_command 一致。
        功能：将原始 shell 命令字符串包裹为一条完整的 sandbox-exec
            shell 命令。
        运行逻辑：
            1. 与 wrap_command 相同的方式生成 SandboxPolicy 与 Seatbelt
               profile 文本。
            2. 选择 shell：macOS 下默认使用 /bin/zsh（系统默认 shell），
               非 macOS 分支理论上不会走到（因 is_available 已限定平台），
               此处用 /bin/bash 兜底。
            3. 对 profile 与原始命令分别用 shlex.quote 转义，拼成
               `sandbox-exec -p <转义后的profile> -- <shell> -c <转义后的命令>`：
               先由 sandbox-exec 注册沙盒策略，再在其中启动 shell 以
               -c 方式执行原始命令字符串。
        出参：str - 可直接通过 `sh -c` 或子进程执行的完整命令字符串。
        """
        policy = SandboxPolicy.from_level(
            self.level,
            allow_network=allow_network,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
        )
        profile = SeatbeltProfileBuilder(policy).build()
        shell = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
        return f"/usr/bin/sandbox-exec -p {shlex.quote(profile)} -- {shell} -c {shlex.quote(command)}"
