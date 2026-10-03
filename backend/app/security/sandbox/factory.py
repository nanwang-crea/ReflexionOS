"""
沙盒工厂模块。

按平台自动选择可用的沙盒后端：Windows 使用 WindowsSandbox，macOS 使用
Seatbelt（sandbox-exec），Linux 使用 Landlock（内核 LSM，通过 bwrap 等
方式施加文件系统访问限制）。若当前主机三者都不可用（如内核版本过低、
缺少必要工具），则退化为 NullSandbox——不做任何隔离，直接透传原始命令，
保证上层调用逻辑无需区分“有沙盒/无沙盒”两种路径。

配置覆盖（2026-10-03，排障用途）：~/.reflexion/config.json 的
sandbox.provider 可强制指定后端（windows/seatbelt/landlock）或强制无沙箱
（null）；默认 auto 保持上述自动探测行为。指定后端不可用时降级为无沙箱
并打 warning——用户已明确表达意图，不静默换其他后端误导排障。
配套开关 sandbox.provider_required（默认 false）：置 true 后指定后端
不可用/初始化失败改为 fail-closed 抛 RuntimeError 拒绝执行，防止
"以为有隔离实际裸奔"（2026-10-03 提交评审 P2 修复）。
"""

from __future__ import annotations

import logging

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.landlock import LandlockSandbox
from app.security.sandbox.sandbox_policy import SandboxLevel
from app.security.sandbox.seatbelt import SeatbeltSandbox
from app.security.sandbox.windows import WindowsSandbox

logger = logging.getLogger(__name__)

# 配置可强制指定的后端映射（显式字典而非 getattr，防配置注入类名）
_NAMED_BACKENDS = {
    "windows": WindowsSandbox,
    "seatbelt": SeatbeltSandbox,
    "landlock": LandlockSandbox,
}


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
    功能：按配置与平台探测返回沙盒后端实例。
    运行逻辑：
        0. 先读 ~/.reflexion/config.json 的 sandbox.provider：
           - "null"：直接返回 NullSandbox（排障用无隔离模式）；
           - 指定后端（windows/seatbelt/landlock）：实例化并探测，可用
             则返回；不可用则打 warning 并降级 NullSandbox——用户已明确
             表达意图，不静默换其他后端误导排障；
           - "auto"（默认/配置读取失败）：走下方自动探测。
        1. 依次尝试实例化 WindowsSandbox（仅 win32 生效）、SeatbeltSandbox
           （仅 macOS 生效）、LandlockSandbox（仅 Linux 生效），并调用其
           is_available() 探测当前主机是否真正支持。
        2. 命中第一个 is_available() 返回 True 的实例即直接返回，不再
           继续尝试后续候选。
        3. 若三者都不可用（探测均为 False），返回 NullSandbox 实例作为
           兜底，保证调用方始终能拿到一个可用的 SandboxProvider。
    出参：SandboxProvider - 选中的具体沙盒实现，或兜底的 NullSandbox。
    """
    provider_name = _configured_provider()
    if provider_name == "null":
        logger.info("配置 sandbox.provider=null：强制使用无沙箱模式（排障用途）")
        return NullSandbox()
    if provider_name in _NAMED_BACKENDS:
        # fail-closed 开关（2026-10-03 评审 P2 修复）：provider_required=True
        # 时指定后端不可用/初始化失败直接抛错拒绝执行，不降级无沙箱——
        # 防止"用户以为有隔离实际裸奔"。默认 False 保持 fail-open 排障语义。
        required = _provider_required()
        try:
            provider = _NAMED_BACKENDS[provider_name](level=level)
            if provider.is_available():
                logger.info("使用配置指定的沙盒后端: %s", provider_name)
                return provider
        except Exception as exc:
            if required:
                raise RuntimeError(
                    f"配置强制指定的沙箱后端 {provider_name} 初始化失败（{exc}），"
                    "且 sandbox.provider_required=true，拒绝在无隔离环境下执行"
                ) from exc
            logger.warning(
                "配置指定的 %s 后端初始化失败（%s），降级为无沙箱",
                provider_name, exc,
            )
            return NullSandbox()
        if required:
            raise RuntimeError(
                f"配置强制指定的沙箱后端 {provider_name} 在当前主机不可用，"
                "且 sandbox.provider_required=true，拒绝在无隔离环境下执行"
            )
        logger.warning(
            "配置指定的 %s 后端在当前主机不可用，降级为无沙箱", provider_name
        )
        return NullSandbox()

    for cls in (WindowsSandbox, SeatbeltSandbox, LandlockSandbox):
        provider = cls(level=level)
        if provider.is_available():
            return provider
    return NullSandbox()


def _configured_provider() -> str:
    """读取配置中的沙箱后端指定（config.json 的 sandbox.provider）。

    入参：无。
    功能：从全局 config_manager 读取 sandbox.provider；配置层任何异常
         （未加载、字段缺失、读取失败）都按 "auto" 处理——沙箱创建不能
         被配置读取失败拖垮。函数内局部导入 config_manager，避免
         config → sandbox 方向的模块级循环依赖风险。
    出参：str - "auto" / "windows" / "seatbelt" / "landlock" / "null"。
    """
    try:
        from app.config.settings import config_manager

        return config_manager.settings.sandbox.provider
    except Exception:
        return "auto"


def _provider_required() -> bool:
    """读取配置中的 fail-closed 开关（config.json 的 sandbox.provider_required）。

    入参：无。
    功能：从全局 config_manager 读取 sandbox.provider_required；配置层任何
         异常都按 False 处理——与 _configured_provider 同理，配置读取失败
         不应改变沙箱创建的默认（fail-open）行为。函数内局部导入
         config_manager，避免模块级循环依赖风险。
    出参：bool - True 表示指定后端不可用时 fail-closed 拒绝执行。
    """
    try:
        from app.config.settings import config_manager

        return config_manager.settings.sandbox.provider_required
    except Exception:
        return False
