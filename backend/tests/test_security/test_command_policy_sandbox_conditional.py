# Windows 第一阶段白名单条件化单测：sandbox_available 时旁路 git-only 限制
import os
import tempfile

from app.security.command_effect_registry import CommandEffectRegistry
from app.security.command_policy import CommandAction, CommandPolicy
from app.security.path_security import PathSecurity
from app.security.permission_mode import PermissionMode
from app.security.shell_security import ShellSecurity


def test_whitelist_bypassed_when_sandbox_available():
    """沙盒可用时，第一阶段白名单不拦截 shell 命令"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        shell_sec = ShellSecurity(platform_name="win32")
        policy = CommandPolicy(
            shell_sec,
            PathSecurity([root_dir], base_dir=root_dir),
            CommandEffectRegistry(),
            permission_mode=PermissionMode.AUTO,
            sandbox_available=True,
        )
        decision = policy.evaluate("cd frontend && dir")
        assert decision.action != CommandAction.DENY, "沙盒可用时不应被白名单 DENY"


def test_whitelist_active_when_no_sandbox():
    """沙盒不可用时，白名单恢复生效"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        shell_sec = ShellSecurity(platform_name="win32")
        policy = CommandPolicy(
            shell_sec,
            PathSecurity([root_dir], base_dir=root_dir),
            CommandEffectRegistry(),
            permission_mode=PermissionMode.AUTO,
            sandbox_available=False,
        )
        decision = policy.evaluate("cd frontend && dir")
        assert decision.action == CommandAction.DENY, "无沙盒时应被白名单 DENY"