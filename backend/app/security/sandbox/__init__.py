"""
沙盒安全隔离模块入口。

汇总并对外暴露 sandbox 子包中的核心类型：跨平台沙盒提供者基类
（SandboxProvider）、沙盒创建工厂（create_sandbox/NullSandbox）、
Linux Landlock 与 macOS Seatbelt 的策略构建器、沙盒策略/级别定义
（SandboxPolicy/SandboxLevel），以及沙盒错误识别工具（SandboxErrorDetector
等）。使用方只需从本包导入，无需关心具体子模块路径。
"""

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.factory import NullSandbox, create_sandbox
from app.security.sandbox.landlock_profile import LandlockProfileBuilder
from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxLevel, SandboxPolicy
from app.security.sandbox.error_detector import SandboxErrorDetector, SandboxErrorInfo, SandboxErrorType
from app.security.sandbox.seatbelt_profile import SeatbeltProfileBuilder

__all__ = [
    "create_sandbox",
    "LandlockProfileBuilder",
    "NullSandbox",
    "ProfileBuilder",
    "SandboxErrorDetector",
    "SandboxErrorInfo",
    "SandboxErrorType",
    "SeatbeltProfileBuilder",
    "SandboxLevel",
    "SandboxPolicy",
    "SandboxProvider",
]
