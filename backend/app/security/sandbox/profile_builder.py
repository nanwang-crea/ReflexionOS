"""
沙盒配置构建器抽象基类。

定义跨平台统一的"策略 -> 平台专属配置"转换接口：输入都是同一个
SandboxPolicy（路径权限、网络权限等抽象策略），但不同平台的沙盒机制
要求完全不同格式的输出——macOS Seatbelt 需要一段 `.sb` 格式的 Scheme
风格策略文本（配合 sandbox-exec 使用），Linux bwrap 需要一组命令行
参数列表。子类（SeatbeltProfileBuilder、LandlockProfileBuilder）各自
实现 build() 完成这一转换，上层调用方无需关心具体平台差异。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.security.sandbox.sandbox_policy import SandboxPolicy


class ProfileBuilder(ABC):
    """
    跨平台沙盒配置构建器基类。

    子类实现 build() 生成平台专属的沙盒配置：Seatbelt 返回 profile
    文本字符串；Landlock/bwrap 返回参数列表。
    """

    def __init__(self, policy: SandboxPolicy) -> None:
        """
        函数名：__init__
        入参：
            - policy (SandboxPolicy): 平台无关的沙盒访问策略（允许的
              读写路径、只读路径、是否允许网络等），由子类的 build()
              读取并翻译为具体平台的配置。
        功能：保存策略对象，供子类构建具体配置时使用。
        运行逻辑：仅做属性赋值。
        出参：无。
        """
        self.policy = policy

    @abstractmethod
    def build(self) -> str | list[str]:
        """
        函数名：build
        入参：无（使用构造时传入的 self.policy）
        功能：将 self.policy 转换为当前平台可直接使用的沙盒配置。
        运行逻辑：由子类实现，具体转换逻辑因平台的沙盒机制而异
            （详见各子类实现，如 SeatbeltProfileBuilder/
            LandlockProfileBuilder）。
        出参：str | list[str]
            - str：macOS Seatbelt 场景，返回 `.sb` 格式的沙盒 profile
              文本，供 `sandbox-exec -p <profile>` 使用。
            - list[str]：Linux bwrap 场景，返回命令行参数列表，供拼接
              到 `bwrap` 命令后执行。
        """
        ...
