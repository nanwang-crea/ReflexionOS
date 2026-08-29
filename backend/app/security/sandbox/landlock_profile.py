"""
Linux bwrap 沙盒参数构建器。

把 SandboxPolicy（抽象策略：允许哪些路径读写、是否允许联网等）翻译成一组
具体的 bwrap 命令行参数。采用"实用主义"策略：默认不与操作系统对抗——把
根目录 `/` 整体以可写方式绑定进沙盒，而不是构造一个从零搭建的最小化文件
系统；仅针对高风险能力做限制：
- 网络：通过 `--unshare-net` 让子进程拥有独立的空网络命名空间，从内核层
  彻底断网（而不是靠防火墙规则过滤）；
- 系统关键路径：对 /usr、/bin 等目录用 `--ro-bind` 覆盖挂载为只读，
  防止沙盒内进程意外或恶意改坏系统文件；
- 敏感路径：对 /etc/shadow、SSH/GPG 密钥目录等强制只读，即使策略整体
  比较宽松也不允许写入这些路径。
这种"默认放开、只堵高危点"的思路与同目录下 SeatbeltProfileBuilder（macOS）
的设计哲学一致，便于两个平台的沙盒行为互相对照理解。
"""

from __future__ import annotations

import os
from typing import ClassVar

from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxPolicy


class LandlockProfileBuilder(ProfileBuilder):
    """
    Linux bwrap 沙盒参数构建器（实用主义模式）。

    设计哲学（与 SeatbeltProfileBuilder 一致）：
    - 不与操作系统对抗——默认把 `/` 以可写方式整体绑定进沙盒；
    - 只限制高风险能力：
        - 网络（通过 --unshare-net 隔离网络命名空间）；
        - 敏感文件路径（用 --ro-bind 覆盖挂载为只读，拒绝写入）；
        - 系统目录写保护（对 /usr、/lib 等用 --ro-bind 覆盖挂载）。
    """

    # 始终以只读方式挂载的系统路径，防止沙盒内进程写坏系统文件
    _SYSTEM_RO_PATHS: ClassVar[tuple[str, ...]] = (
        "/usr", "/bin", "/sbin", "/lib", "/lib64",
    )

    # 即使在宽松模式下也始终拒绝写入的敏感路径（密码文件、SSH/GPG 密钥等）
    _DENIED_PATHS: ClassVar[tuple[str, ...]] = (
        "/etc/shadow", "/etc/ssh", "/root/.ssh", "/root/.gnupg",
    )

    def __init__(self, policy: SandboxPolicy, *, cwd: str) -> None:
        """
        函数名：__init__
        入参：
            - policy (SandboxPolicy): 沙盒访问策略（允许的路径、是否
              允许网络等），由上层根据 SandboxLevel 生成
            - cwd (str): 沙盒内命令的工作目录，构建时会转换为
              `--chdir` 参数
        功能：初始化构建器状态，为后续 build() 组装 bwrap 参数列表做准备。
        运行逻辑：调用父类构造函数保存 policy，再记录 cwd 并初始化空的
            参数累积列表 self.args。
        出参：无。
        """
        super().__init__(policy)
        self.cwd = cwd
        self.args: list[str] = []

    def build(self) -> list[str]:
        """
        函数名：build
        入参：无（使用构造时传入的 self.policy / self.cwd）
        功能：按固定顺序依次调用各个子步骤，组装出完整的 bwrap 命令行
            参数列表（模板方法模式）。
        运行逻辑：
            1. _base()：写入基础隔离参数（子进程随父进程退出而终止）。
            2. _network()：按策略决定是否隔离网络命名空间。
            3. _binds()：绑定文件系统（默认整体可写绑定 `/`，再覆盖
               系统路径、敏感路径为只读，最后叠加调用方指定的
               允许写/只读路径）。
            4. _virtual_fs()：挂载 /proc、/dev、/tmp 等虚拟文件系统，
               保证沙盒内进程能正常运行（很多程序依赖这些路径存在）。
            5. _chdir()：设置沙盒内命令的初始工作目录。
        出参：list[str] - 完整的 bwrap 参数列表（不含 "bwrap" 本身和
            "--" 分隔符，调用方负责拼接成最终 argv）。
        """
        self._base()
        self._network()
        self._binds()
        self._virtual_fs()
        self._chdir()
        return self.args

    # -- template methods ---------------------------------------------------

    def _base(self) -> None:
        """
        函数名：_base
        入参：无
        功能：写入最基础的隔离参数，不做激进限制。
        运行逻辑：追加 `--die-with-parent`，让沙盒子进程在父进程（本
            服务的执行进程）退出时也一并被杀死，避免孤儿进程残留。
        出参：无（结果追加到 self.args）。
        """
        self.args.append("--die-with-parent")

    def _network(self) -> None:
        """
        函数名：_network
        入参：无
        功能：根据策略决定是否切断沙盒内进程的网络访问能力。
        运行逻辑：若 policy.allow_network 为 False，追加 `--unshare-net`，
            让子进程进入一个新的、没有任何网络接口的网络命名空间，
            从内核层面彻底断网（而非依赖应用层过滤，更难被绕过）。
        出参：无（结果追加到 self.args）。
        """
        if not self.policy.allow_network:
            self.args.append("--unshare-net")

    def _binds(self) -> None:
        """
        函数名：_binds
        入参：无
        功能：组装文件系统绑定相关参数，实现"默认放开、按需收紧"的
            访问控制。
        运行逻辑（按顺序叠加，后面的挂载会覆盖前面同路径的挂载）：
            1. 若根目录 `/` 存在，先用 `--bind / /` 把整个文件系统
               以可写方式绑定进沙盒（实用主义默认：不做最小化文件系统）。
            2. 对 _SYSTEM_RO_PATHS（/usr、/bin 等）中存在的目录，用
               `--ro-bind` 重新挂载为只读，覆盖掉第 1 步的可写绑定，
               防止系统文件被沙盒内进程改坏。
            3. 对 _DENIED_PATHS（/etc/shadow、SSH/GPG 密钥目录等）中
               存在的路径，同样用 `--ro-bind` 强制只读。
            4. 对 policy.allowed_paths 中调用方显式指定的路径，用
               `--bind` 绑定为可写（典型场景：项目工作目录）。
            5. 对 policy.read_only_paths 中调用方指定的路径，用
               `--ro-bind` 绑定为只读。
        出参：无（结果追加到 self.args）。
        """

        # Bind entire root filesystem as writable (pragmatic: allow default)
        if os.path.isdir("/"):
            self.args.extend(["--bind", "/", "/"])

        # Override system paths as read-only (prevent system corruption)
        for prefix in self._SYSTEM_RO_PATHS:
            if os.path.isdir(prefix):
                self.args.extend(["--ro-bind", prefix, prefix])

        # Override sensitive paths as read-only
        for p in self._DENIED_PATHS:
            if os.path.exists(p):
                self.args.extend(["--ro-bind", p, p])

        # Explicit allowed paths (writable, for project directories)
        for p in self.policy.allowed_paths:
            self.args.extend(["--bind", p, p])

        # Read-only paths (caller-specified)
        for p in self.policy.read_only_paths:
            self.args.extend(["--ro-bind", p, p])

    def _virtual_fs(self) -> None:
        """
        函数名：_virtual_fs
        入参：无
        功能：挂载沙盒内进程正常运行所需的虚拟文件系统。
        运行逻辑：依次追加 `--proc /proc`（挂载独立的 /proc，隔离进程
            可见性）、`--dev /dev`（提供最小化的设备节点）、
            `--tmpfs /tmp`（提供内存临时文件系统，沙盒退出后自动清空，
            不污染宿主机 /tmp）。
        出参：无（结果追加到 self.args）。
        """
        self.args.extend(["--proc", "/proc"])
        self.args.extend(["--dev", "/dev"])
        self.args.extend(["--tmpfs", "/tmp"])

    def _chdir(self) -> None:
        """
        函数名：_chdir
        入参：无
        功能：设置沙盒内命令启动后的初始工作目录。
        运行逻辑：追加 `--chdir <self.cwd>`，bwrap 会在完成所有挂载后
            将进程工作目录切换到该路径再执行目标命令。
        出参：无（结果追加到 self.args）。
        """
        self.args.extend(["--chdir", self.cwd])
