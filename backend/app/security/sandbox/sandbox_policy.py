"""
沙盒策略定义模块。

提供平台无关的沙盒策略抽象：SandboxLevel 是面向使用者的“严格程度”档位
（strict/dev/permissive），SandboxPolicy 是从档位派生出的具体参数集合
（是否允许任意执行子进程、是否允许 IPC/mach、是否允许用户目录读写、是否
允许网络、具体的允许路径/只读路径列表）。各平台的 ProfileBuilder 子类
只读取 SandboxPolicy 这一份具体参数来生成 Seatbelt profile 或 bwrap
参数，从不直接解释 SandboxLevel——这样新增平台后端时只需实现"如何落地
SandboxPolicy"，不用重复"档位应该对应什么权限"的判断逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SandboxLevel(str, Enum):
    """
    跨平台沙盒严格程度档位。

    继承 str 是为了让 SandboxLevel("dev") 这种从字符串值构造的写法可用
    （便于从配置文件/环境变量读取档位名称后直接转换）。
    """

    STRICT = "strict"           # 最小权限：仅系统只读 + 项目目录可写 + 受限的进程执行
    DEV = "dev"                 # 开发默认档：用户目录可读写、可执行任意程序、允许 IPC/mach
    PERMISSIVE = "permissive"   # 调试档：几乎放开所有权限，但仍保留沙盒边界（不是完全无沙盒）


@dataclass
class SandboxPolicy:
    """
    由 SandboxLevel + 调用方覆盖参数推导出的具体沙盒参数集合。

    各平台的 ProfileBuilder 只读取本 dataclass 的字段来生成配置，
    不会反过来直接解释 SandboxLevel 枚举值。
    """

    # 进程相关
    allow_process_exec_all: bool = False  # True 表示可执行任意程序；False 表示仅限系统路径下的程序
    allow_ipc: bool = False
    allow_mach: bool = False              # macOS 专属能力（Mach 端口通信），bwrap/Linux 会忽略此项

    # 文件系统相关
    allow_user_read: bool = False
    allow_user_write: bool = False
    allow_user_exec: bool = False

    # 网络相关
    allow_network: bool = False

    # 路径相关
    allowed_paths: list[str] = field(default_factory=list)
    read_only_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_level(
        cls,
        level: SandboxLevel = SandboxLevel.DEV,
        *,
        allow_network: bool = False,
        allowed_paths: list[str] | None = None,
        read_only_paths: list[str] | None = None,
    ) -> SandboxPolicy:
        """
        函数名：from_level
        入参：
            - level (SandboxLevel): 沙盒严格程度档位，默认 SandboxLevel.DEV。
              STRICT 会关闭用户目录读写、IPC、mach 以及不受限的进程执行；
              DEV 和 PERMISSIVE 都会开启这些能力（二者目前派生出的策略
              相同，差异主要体现在各平台 ProfileBuilder 对细节的处理上）。
            - allow_network (bool): 是否允许对外发起网络连接，直接透传
              到生成的策略中。
            - allowed_paths (list[str] | None): 调用方指定的可读写目录
              列表，为 None 时按空列表处理。
            - read_only_paths (list[str] | None): 调用方指定的只读目录
              列表，为 None 时按空列表处理。
        功能：根据严格程度档位与调用方的显式覆盖参数，推导出一份具体的
            SandboxPolicy。
        运行逻辑：
            1. 判断 level 是否为 STRICT，得到布尔值 strict。
            2. 除 allow_network/allowed_paths/read_only_paths 三项直接
               采用调用方传入值外，其余能力字段统一取 `not strict`——
               即 STRICT 档位下全部关闭，DEV/PERMISSIVE 档位下全部开启。
        出参：SandboxPolicy - 派生出的具体策略实例，供各平台
            ProfileBuilder 读取使用。
        """
        strict = level == SandboxLevel.STRICT
        return cls(
            allow_process_exec_all=not strict,
            allow_ipc=not strict,
            allow_mach=not strict,
            allow_user_read=not strict,
            allow_user_write=not strict,    # DEV + PERMISSIVE both allow /Users write
            allow_user_exec=not strict,
            allow_network=allow_network,
            allowed_paths=allowed_paths or [],
            read_only_paths=read_only_paths or [],
        )
