"""
macOS Seatbelt 沙盒 profile 构建器。

把 SandboxPolicy（抽象策略）翻译成一段 `.sb` 格式的 Seatbelt 策略文本，
供 `sandbox-exec -p <profile>` 加载使用。Seatbelt 策略文本采用 Scheme
风格的 S 表达式语法，每条语句形如 `(allow xxx ...)` 或 `(deny xxx ...)`，
内核按声明顺序叠加规则（后声明的 deny 可以覆盖前面更宽泛的 allow）。
采用"实用主义"策略：先 `(allow default)` 放开几乎所有能力（不与操作系统
对抗），再针对高风险点逐条 `(deny ...)` 收紧——网络访问、系统目录写入、
用户 SSH/GPG 等敏感文件读取。这种"默认放开、只堵高危点"的思路与同目录下
LandlockProfileBuilder（Linux）的设计哲学一致。
"""

from __future__ import annotations

from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxPolicy


class SeatbeltProfileBuilder(ProfileBuilder):
    """
    Agent Shell 场景下的 macOS Seatbelt profile 构建器（实用主义模式）。

    设计哲学：
    - 不与操作系统对抗（默认放开 allow default）；
    - 只限制高风险能力：
        - 网络；
        - 敏感文件路径；
        - 系统目录写入。
    """

    def __init__(self, policy: SandboxPolicy) -> None:
        """
        函数名：__init__
        入参：
            - policy (SandboxPolicy): 沙盒访问策略（允许的路径、是否
              允许网络等），由上层根据 SandboxLevel 生成
        功能：初始化构建器状态，为后续 build() 组装 profile 文本行做准备。
        运行逻辑：调用父类构造函数保存 policy，再初始化空的文本行
            累积列表 self.lines。
        出参：无。
        """
        super().__init__(policy)
        self.lines: list[str] = []

    def build(self) -> str:
        """
        函数名：build
        入参：无（使用构造时传入的 self.policy）
        功能：按固定顺序依次调用各个子步骤，组装出完整的 Seatbelt
            profile 文本（模板方法模式）。
        运行逻辑：
            1. _header()：写入 profile 版本声明与默认放开规则。
            2. _temp()：显式放开临时目录读写（部分工具强依赖）。
            3. _paths()：基于"拒绝优先"模型收紧危险路径（系统目录写、
               SSH/GPG 密钥读），再叠加调用方指定的允许路径。
            4. _network()：按策略允许或禁止网络访问。
            5. _process()：放开子进程执行/fork 能力，避免破坏依赖
               子进程调用的工具链生态。
            6. _misc()：放开信号发送、sysctl 只读等杂项能力。
            每个子步骤把生成的策略语句追加到 self.lines，最终按换行符
            拼接成完整文本。
        出参：str - 完整的 `.sb` 格式 Seatbelt profile 文本，可直接
            传给 `sandbox-exec -p`。
        """
        self._header()
        self._temp()
        self._paths()
        self._network()
        self._process()
        self._misc()
        return "\n".join(self.lines)

    # ---------------- core ----------------

    def _header(self) -> None:
        """
        函数名：_header
        入参：无
        功能：写入 Seatbelt profile 的版本声明与默认策略。
        运行逻辑：追加 `(version 1)` 声明 profile 语法版本；追加
            `(allow default)` 作为 Agent Shell 模式的核心——默认放开
            几乎所有操作，后续步骤只针对高风险点做 deny 收紧。
        出参：无（结果追加到 self.lines）。
        """
        self.lines.append("(version 1)")
        # ✅ Agent shell 模式核心：默认允许
        self.lines.append("(allow default)")

    # ---------------- filesystem ----------------

    def _temp(self) -> None:
        """
        函数名：_temp
        入参：无
        功能：显式放开常见临时目录的读写权限。
        运行逻辑：对 /tmp、/private/tmp、/var/folders（macOS 实际的
            临时文件根路径，/tmp 通常是指向它的符号链接）分别追加
            `(allow file-read* file-write* (subpath "..."))`，确保依赖
            临时文件的工具（如某些语言运行时、包管理器）能正常工作。
        出参：无（结果追加到 self.lines）。
        """
        for p in ("/tmp", "/private/tmp", "/var/folders"):
            self.lines.append(f'(allow file-read* file-write* (subpath "{p}"))')

    def _paths(self) -> None:
        """
        函数名：_paths
        入参：无
        功能：基于"拒绝优先"模型，仅收紧真正危险的文件路径，其余沿用
            _header 中 (allow default) 放开的默认权限。
        运行逻辑：
            1. 追加 deny 规则禁止写入 /System、/usr（防止破坏系统文件；
               读取不受限，仅禁写）。
            2. 追加 deny 规则禁止读取所有用户的 ~/.ssh、~/.gnupg 目录
               （SSH 私钥、GPG 密钥等敏感凭据）。
            3. 对 policy.allowed_paths 中调用方指定的路径，追加 allow
               规则显式放开读写（典型场景：项目工作目录，增强可控性
               和可读性，即使 default 已经放开也显式声明一次）。
            4. 对 policy.read_only_paths 中调用方指定的路径，追加 allow
               规则仅放开读取。
        出参：无（结果追加到 self.lines）。
        """

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
        """
        函数名：_process
        入参：无
        功能：放开子进程执行与 fork 能力，不做重度限制。
        运行逻辑：追加 `(allow process-exec)` 和 `(allow process-fork)`。
            许多开发工具链（构建脚本、包管理器、解释器）内部会 fork/exec
            子进程，若严格限制会破坏整个生态的可用性，因此这里选择放开，
            风险主要通过网络/敏感路径限制来兜底。
        出参：无（结果追加到 self.lines）。
        """
        self.lines.append("(allow process-exec)")
        self.lines.append("(allow process-fork)")

    # ---------------- network ----------------

    def _network(self) -> None:
        """
        函数名：_network
        入参：无
        功能：按策略决定是否允许网络访问。
        运行逻辑：policy.allow_network 为 True 时追加
            `(allow network*)` 放开所有网络操作；否则追加
            `(deny network*)` 作为核心隔离手段，禁止一切网络访问
            （包括 socket 创建、连接、DNS 解析等）。
        出参：无（结果追加到 self.lines）。
        """
        if self.policy.allow_network:
            self.lines.append("(allow network*)")
        else:
            # 🔴 核心隔离：禁止网络
            self.lines.append("(deny network*)")

    # ---------------- misc ----------------

    def _misc(self) -> None:
        """
        函数名：_misc
        入参：无
        功能：放开信号发送与只读 sysctl 访问等杂项系统能力。
        运行逻辑：追加 `(allow signal)`（允许发送/接收信号，进程管理、
            超时终止等场景需要）和 `(allow sysctl-read)`（允许只读查询
            系统内核参数，很多运行时/工具启动时会探测系统信息）。
        出参：无（结果追加到 self.lines）。
        """
        self.lines.append("(allow signal)")
        self.lines.append("(allow sysctl-read)")