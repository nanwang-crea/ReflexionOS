"""
沙盒错误识别模块。

命令在沙盒中执行失败后，仅凭 returncode 无法区分"是沙盒拦截的"还是"程序自身
的正常错误"。本模块通过匹配 stderr 中的特征文本，识别失败是否由沙盒的网络
限制或文件路径限制导致：
- macOS Seatbelt（sandbox-exec）会在 stderr 输出形如
  "deny(1) network-outbound" 或 "deny file-read* (subpath ...)" 的拒绝日志；
- Linux bwrap/Landlock 场景下沙盒本身不总是打印显式拒绝信息，而是让底层网络
  调用失败，因此改用 DNS 解析失败、连接被拒等通用网络异常特征来间接推断；
- 部分场景（如 Python urllib/requests 抛出的异常文本）与具体沙盒实现无关，
  按“通用网络错误关键词 + 命令是否常需要联网”的经验规则做兜底判断。
识别结果（SandboxErrorInfo）用于上层向用户提示“该失败可能是沙盒策略限制，
可尝试放宽网络/路径权限后重试”，而不是让用户误以为是程序本身的 bug。
"""

from __future__ import annotations

import enum
import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.security.command_effect_registry import CommandEffectRegistry


class SandboxErrorType(str, enum.Enum):
    """沙盒拦截导致的错误类型：网络被拒绝 / 路径访问被拒绝。"""
    NETWORK_DENIED = "network_denied"
    PATH_DENIED = "path_denied"


@dataclass
class SandboxErrorInfo:
    """
    沙盒错误识别结果。

    error_type: 识别出的错误类型（网络拒绝 / 路径拒绝）
    denied_paths: 被拒绝访问的具体路径列表（仅路径拒绝场景会填充）
    original_stderr: 原始 stderr 文本，供上层展示或进一步排查
    confidence: 识别置信度，"high" 表示匹配到明确的沙盒拒绝日志，
        "medium" 表示基于通用网络错误特征的间接推断
    """
    error_type: SandboxErrorType
    denied_paths: list[str] = field(default_factory=list)
    original_stderr: str = ""
    confidence: Literal["high", "medium"] = "medium"


class SandboxErrorDetector:
    """
    沙盒错误检测器：按平台匹配 stderr 特征，判断命令失败是否由沙盒策略导致。

    各平台/场景的正则特征库：
    - SEATBELT_NETWORK_PATTERNS / SEATBELT_PATH_PATTERNS：macOS sandbox-exec
      在拒绝网络或文件访问时输出的明确日志格式（高置信度）。
    - BWRAP_NETWORK_PATTERNS：Linux bwrap 环境下网络被隔离时，网络库抛出的
      系统级错误提示（中等置信度，因为并非沙盒专属日志）。
    - PYTHON_NETWORK_ERROR_PATTERNS：Python 标准库/常见第三方库
      （socket、urllib、requests）在无网络时抛出的异常文本，跨平台通用。
    - GENERIC_NETWORK_ERROR_PATTERNS：不限语言/工具的通用网络错误关键词，
      仅在命令注册表中标记为“通常需要联网”时才采信，避免误判为沙盒问题。
    """

    SEATBELT_NETWORK_PATTERNS = [
        re.compile(r"deny\s+network", re.IGNORECASE),
        re.compile(r"sandbox-exec.*denied.*network", re.IGNORECASE),
    ]
    SEATBELT_PATH_PATTERNS = [
        re.compile(r'deny\s+file-read\*\s*\(subpath\s+"([^"]+)"\)', re.IGNORECASE),
        re.compile(r'deny\s+file-write\*\s*.*\(subpath\s+"([^"]+)"\)', re.IGNORECASE),
    ]
    BWRAP_NETWORK_PATTERNS = [
        re.compile(r"Network is unreachable", re.IGNORECASE),
        re.compile(r"Could not resolve host", re.IGNORECASE),
        re.compile(r"Temporary failure in name resolution", re.IGNORECASE),
    ]
    PYTHON_NETWORK_ERROR_PATTERNS = [
        re.compile(r"socket\.gaierror.*Errno\s+8", re.IGNORECASE),
        re.compile(r"nodename nor servname provided", re.IGNORECASE),
        re.compile(r"urlopen error.*Errno\s+8", re.IGNORECASE),
        re.compile(r"URLError.*nodename nor servname", re.IGNORECASE),
        re.compile(r"NewConnectionError", re.IGNORECASE),
        re.compile(r"MaxRetryError.*ConnectionError", re.IGNORECASE),
        re.compile(r"requests\.exceptions\.ConnectionError", re.IGNORECASE),
        re.compile(r"Failed to establish a new connection", re.IGNORECASE),
        re.compile(r"Name or service not known", re.IGNORECASE),
        re.compile(r"getaddrinfo\s+failed", re.IGNORECASE),
    ]
    GENERIC_NETWORK_ERROR_PATTERNS = [
        re.compile(r"Connection refused", re.IGNORECASE),
        re.compile(r"Connection timed? ?out", re.IGNORECASE),
        re.compile(r"Network is (unreachable|down)", re.IGNORECASE),
        re.compile(r"Could not resolve (host|hostname)", re.IGNORECASE),
        re.compile(r"Name or service not known", re.IGNORECASE),
        re.compile(r"Temporary failure in name resolution", re.IGNORECASE),
    ]

    def detect(
        self,
        returncode: int,
        stderr: str,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
        platform: str = sys.platform,
    ) -> SandboxErrorInfo | None:
        """
        函数名：detect
        入参：
            - returncode (int): 命令的进程返回码
            - stderr (str): 命令执行的标准错误输出
            - command_argv (list[str] | None): 命令及参数列表，用于结合命令
              注册表判断该命令是否通常需要联网
            - registry (CommandEffectRegistry | None): 命令效果注册表，
              提供“该命令是否常需要网络”等元信息，辅助通用网络错误的判定
            - platform (str): 当前平台标识，默认取 sys.platform（"darwin"/
              "linux"/其他）
        功能：判断一次失败的命令执行是否由沙盒的网络或路径限制导致。
        运行逻辑：
            1. returncode 为 0（成功）或 stderr 为空时，直接判定为非沙盒错误。
            2. 按 platform 分派：macOS 走 Seatbelt 特征匹配，Linux 走
               bwrap 特征匹配，其他平台不做识别。
        出参：SandboxErrorInfo | None - 识别出的沙盒错误信息；无法判定或
            确认不是沙盒问题时返回 None。
        """
        if returncode == 0:
            return None

        if not stderr:
            return None

        if platform == "darwin":
            return self._detect_seatbelt(stderr, returncode, command_argv, registry)
        elif platform == "linux":
            return self._detect_bwrap(stderr, returncode, command_argv, registry)
        else:
            return None

    def _detect_seatbelt(
        self,
        stderr: str,
        returncode: int,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
    ) -> SandboxErrorInfo | None:
        """
        函数名：_detect_seatbelt
        入参：
            - stderr (str): 命令的标准错误输出
            - returncode (int): 命令返回码（本方法未直接使用，仅透传给
              通用网络错误兜底判断）
            - command_argv (list[str] | None): 命令及参数列表
            - registry (CommandEffectRegistry | None): 命令效果注册表
        功能：在 macOS 平台上，按 Seatbelt（sandbox-exec）的特征日志识别
            网络拒绝或路径拒绝错误。
        运行逻辑：
            1. 先匹配 Seatbelt 明确的网络拒绝日志格式，命中则高置信度返回
               NETWORK_DENIED。
            2. 再匹配 Python 网络异常特征（无网络时常见的库异常文本），
               命中则高置信度返回 NETWORK_DENIED。
            3. 匹配 Seatbelt 路径拒绝日志，提取所有被拒绝的具体路径，
               命中则高置信度返回 PATH_DENIED（附带 denied_paths）。
            4. 以上均未命中时，退化到通用网络错误兜底判断。
        出参：SandboxErrorInfo | None - 识别结果；均未命中时返回
            _detect_generic_network 的结果（可能仍为 None）。
        """
        for pattern in self.SEATBELT_NETWORK_PATTERNS:
            if pattern.search(stderr):
                return SandboxErrorInfo(
                    error_type=SandboxErrorType.NETWORK_DENIED,
                    original_stderr=stderr,
                    confidence="high",
                )

        for pattern in self.PYTHON_NETWORK_ERROR_PATTERNS:
            if pattern.search(stderr):
                return SandboxErrorInfo(
                    error_type=SandboxErrorType.NETWORK_DENIED,
                    original_stderr=stderr,
                    confidence="high",
                )

        denied_paths = []
        for pattern in self.SEATBELT_PATH_PATTERNS:
            for match in pattern.finditer(stderr):
                denied_paths.append(match.group(1))
        if denied_paths:
            return SandboxErrorInfo(
                error_type=SandboxErrorType.PATH_DENIED,
                denied_paths=denied_paths,
                original_stderr=stderr,
                confidence="high",
            )

        return self._detect_generic_network(stderr, returncode, command_argv, registry)

    def _detect_bwrap(
        self,
        stderr: str,
        returncode: int,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
    ) -> SandboxErrorInfo | None:
        """
        函数名：_detect_bwrap
        入参：
            - stderr (str): 命令的标准错误输出
            - returncode (int): 命令返回码（透传给通用网络错误兜底判断）
            - command_argv (list[str] | None): 命令及参数列表
            - registry (CommandEffectRegistry | None): 命令效果注册表
        功能：在 Linux 平台上（bwrap/Landlock 沙盒），按网络异常特征识别
            网络拒绝错误。与 Seatbelt 不同，bwrap 通常不产生显式的“拒绝”
            日志，而是直接让网络系统调用失败，因此这里没有路径拒绝的
            专门识别（Landlock 的路径拒绝一般表现为常规 Permission denied，
            难以与真实权限问题区分，故不在此按“沙盒问题”归类）。
        运行逻辑：
            1. 匹配 bwrap 场景下常见的网络不可达/DNS 解析失败提示，命中则
               中等置信度返回 NETWORK_DENIED（因为这些提示并非沙盒专属）。
            2. 匹配 Python 网络异常特征，命中则高置信度返回 NETWORK_DENIED。
            3. 均未命中时，退化到通用网络错误兜底判断。
        出参：SandboxErrorInfo | None - 识别结果；均未命中时返回
            _detect_generic_network 的结果（可能仍为 None）。
        """
        for pattern in self.BWRAP_NETWORK_PATTERNS:
            if pattern.search(stderr):
                return SandboxErrorInfo(
                    error_type=SandboxErrorType.NETWORK_DENIED,
                    original_stderr=stderr,
                    confidence="medium",
                )

        for pattern in self.PYTHON_NETWORK_ERROR_PATTERNS:
            if pattern.search(stderr):
                return SandboxErrorInfo(
                    error_type=SandboxErrorType.NETWORK_DENIED,
                    original_stderr=stderr,
                    confidence="high",
                )

        return self._detect_generic_network(stderr, returncode, command_argv, registry)

    def _detect_generic_network(
        self,
        stderr: str,
        returncode: int,
        command_argv: list[str] | None = None,
        registry: CommandEffectRegistry | None = None,
    ) -> SandboxErrorInfo | None:
        """
        函数名：_detect_generic_network
        入参：
            - stderr (str): 命令的标准错误输出
            - returncode (int): 命令返回码（当前实现未直接使用，保留以与
              调用签名一致，便于未来结合返回码细化判断）
            - command_argv (list[str] | None): 命令及参数列表，用于取
              argv[0] 查询命令注册表
            - registry (CommandEffectRegistry | None): 命令效果注册表
        功能：跨平台的通用网络错误兜底识别，仅在“命令本身通常需要联网”时
            才采信，避免把程序自身逻辑错误误判为沙盒网络限制。
        运行逻辑：
            1. 检查 stderr 是否命中任意通用网络错误关键词，未命中直接
               返回 None。
            2. 命中关键词后，查询命令注册表：若 argv[0] 对应的命令条目
               标记了 often_needs_network=True，才认为“很可能是沙盒把
               网络挡住了”。
            3. 满足上述条件返回中等置信度的 NETWORK_DENIED，否则返回
               None（不打沙盒的标签，交由上层按普通错误处理）。
        出参：SandboxErrorInfo | None - 满足网络关键词 + 命令通常需要联网
            两个条件时返回中等置信度的 NETWORK_DENIED，否则返回 None。
        """
        has_network_keyword = any(p.search(stderr) for p in self.GENERIC_NETWORK_ERROR_PATTERNS)
        if not has_network_keyword:
            return None

        often_needs = False
        if registry and command_argv and len(command_argv) > 0:
            entry = registry.lookup(command_argv[0])
            if entry and entry.often_needs_network:
                often_needs = True

        if often_needs:
            return SandboxErrorInfo(
                error_type=SandboxErrorType.NETWORK_DENIED,
                original_stderr=stderr,
                confidence="medium",
            )

        return None
