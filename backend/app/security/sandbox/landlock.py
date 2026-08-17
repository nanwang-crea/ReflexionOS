"""
Linux 平台沙盒实现（基于 bubblewrap / bwrap）。

类名叫 Landlock，实际是通过命令行工具 bwrap（bubblewrap）来落地隔离：
bwrap 底层综合利用 Linux 内核的 mount 命名空间、user 命名空间等机制，
将真实文件系统重新挂载为一套受限的视图（只读绑定、可写绑定、隐藏路径等），
效果上等价于内核级的 Landlock 文件访问控制，但通过更成熟、跨内核版本
兼容性更好的 bwrap 命令来实现，不需要直接调用 Landlock 系统调用。
命令被 wrap 后，实际执行的是 `bwrap <一堆挂载/网络参数> -- <原始命令>`，
bwrap 先根据参数搭好隔离环境，再在其中 exec 原始命令。
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.landlock_profile import LandlockProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxLevel, SandboxPolicy


class LandlockSandbox(SandboxProvider):
    """基于 bubblewrap（bwrap）的 Linux 沙盒实现。"""

    def __init__(self, level: SandboxLevel = SandboxLevel.DEV) -> None:
        """
        函数名：__init__
        入参：
            - level (SandboxLevel): 沙盒严格程度级别，默认 SandboxLevel.DEV，
              后续 wrap_command/wrap_shell_command 会据此推导具体访问策略。
        功能：保存沙盒级别配置，供后续构建 bwrap 参数时使用。
        运行逻辑：仅做属性赋值，不涉及任何系统探测或副作用。
        出参：无。
        """
        self.level = level

    def is_available(self) -> bool:
        """
        函数名：is_available
        入参：无
        功能：探测当前主机是否具备使用本沙盒后端的条件。
        运行逻辑：
            1. 非 Linux 平台直接判定不可用。
            2. 系统 PATH 中找不到 bwrap 可执行文件，判定不可用（bwrap
               通常需要单独安装，不是所有 Linux 发行版都预装）。
            3. 前两项都满足后，再实际跑一次 bwrap 做真机验证（有的内核
               禁用了 unprivileged user namespaces，仅凭“文件存在”不足以
               确认可用）。
        出参：bool - True 表示当前主机可以使用 bwrap 沙盒，False 表示不可用。
        """
        if sys.platform != "linux":
            return False
        if not shutil.which("bwrap"):
            return False
        return self._check_bwrap_support()

    def _check_bwrap_support(self) -> bool:
        """
        函数名：_check_bwrap_support
        入参：无
        功能：通过实际执行一次最小化的 bwrap 命令，验证当前内核真的支持
            bwrap 所需的命名空间机制（而不仅仅是二进制文件存在）。
        运行逻辑：执行 `bwrap --ro-bind / / -- true`——把根目录只读绑定到
            自身、什么隔离都不额外做，只是验证 bwrap 能否成功启动一个子
            进程并让它以返回码 0 退出；设置 5 秒超时防止异常卡死；捕获
            OSError（如权限问题）和超时异常，两者都视为不可用。
        出参：bool - True 表示 bwrap 探测命令成功执行且返回码为 0；
            False 表示执行失败、超时或返回非 0。
        """
        try:
            result = subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", "--", "true"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
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
        入参：见基类 SandboxProvider.wrap_command——argv 为原始命令，
            cwd 为工作目录，allowed_paths/read_only_paths 控制可写/只读
            路径范围，allow_network/allow_ipc 控制网络与 IPC 权限。
        功能：将原始 argv 命令包裹为一条完整的 bwrap 命令。
        运行逻辑：
            1. 根据 level 与传入的路径/网络参数，通过 SandboxPolicy.from_level
               生成具体的沙盒策略对象。
            2. 用 LandlockProfileBuilder 将策略翻译为一组 bwrap 命令行参数
               （挂载绑定、网络命名空间等）。
            3. 拼接成最终 argv：["bwrap"] + bwrap参数 + ["--"] + 原始命令；
               "--" 是 bwrap 的分隔符，之后的内容才是真正要在沙盒里执行的
               命令本身。
        出参：list[str] - 可直接传给 subprocess 执行的新 argv 列表。
        """
        policy = SandboxPolicy.from_level(
            self.level,
            allow_network=allow_network,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
        )
        bwrap_args = LandlockProfileBuilder(policy, cwd=cwd).build()
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
        """
        函数名：wrap_shell_command
        入参：见基类 SandboxProvider.wrap_shell_command——command 为原始
            shell 命令字符串，其余参数含义与 wrap_command 一致。
        功能：将原始 shell 命令字符串包裹为一条完整的 bwrap shell 命令。
        运行逻辑：
            1. 与 wrap_command 相同的方式生成 SandboxPolicy 与 bwrap 参数。
            2. 对每个 bwrap 参数用 shlex.quote 转义，拼接为安全的参数字符串
               （防止路径等内容中包含空格/特殊字符破坏 shell 解析）。
            3. 最终拼成
               `bwrap <转义后的参数> -- /bin/bash -c <转义后的原始命令>`：
               先由 bwrap 搭好沙盒环境，再在其中启动 bash 以 -c 方式执行
               原始命令字符串。
        出参：str - 可直接通过 `sh -c` 或子进程执行的完整命令字符串。
        """
        policy = SandboxPolicy.from_level(
            self.level,
            allow_network=allow_network,
            allowed_paths=allowed_paths,
            read_only_paths=read_only_paths,
        )
        bwrap_args = LandlockProfileBuilder(policy, cwd=cwd).build()
        args_str = " ".join(shlex.quote(a) for a in bwrap_args)
        shell = "/bin/bash"
        return f"bwrap {args_str} -- {shell} -c {shlex.quote(command)}"
