# Windows 沙盒集成测试：覆盖 permission_mode × sandbox_available 组合矩阵。
# 使用 CommandPolicy 层（不涉及真实的 ShellTool/approval 通路），验证 resolve_action
# 在 Windows 平台下的决策是否与 spec 一致。

import os
import tempfile

import pytest

from app.security.command_effect_registry import CommandEffectRegistry
from app.security.command_policy import CommandAction, CommandPolicy
from app.security.path_security import PathSecurity
from app.security.permission_mode import PermissionMode
from app.security.shell_security import ShellSecurity


@pytest.fixture
def win_policy_auto_sandbox():
    """Windows 平台 + AUTO 模式 + 沙盒可用"""
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
        yield policy


@pytest.fixture
def win_policy_yolo_sandbox():
    """Windows 平台 + YOLO 模式 + 沙盒可用"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        shell_sec = ShellSecurity(platform_name="win32")
        policy = CommandPolicy(
            shell_sec,
            PathSecurity([root_dir], base_dir=root_dir),
            CommandEffectRegistry(),
            permission_mode=PermissionMode.YOLO,
            sandbox_available=True,
        )
        yield policy


@pytest.fixture
def win_policy_yolo_no_sandbox():
    """Windows 平台 + YOLO 模式 + 沙盒不可用"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        shell_sec = ShellSecurity(platform_name="win32")
        policy = CommandPolicy(
            shell_sec,
            PathSecurity([root_dir], base_dir=root_dir),
            CommandEffectRegistry(),
            permission_mode=PermissionMode.YOLO,
            sandbox_available=False,
        )
        yield policy


@pytest.fixture
def win_policy_auto_no_sandbox():
    """Windows 平台 + AUTO 模式 + 沙盒不可用"""
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
        yield policy


def test_dir_read_only_auto(win_policy_auto_sandbox):
    """#1 AUTO dir → READ_ONLY → ALLOW"""
    decision = win_policy_auto_sandbox.evaluate("dir")
    assert decision.action != CommandAction.DENY


def test_runas_always_deny_yolo(win_policy_yolo_sandbox):
    """#7 YOLO runas → ESCALATE → DENY"""
    decision = win_policy_yolo_sandbox.evaluate("runas /user:admin cmd")
    assert decision.action == CommandAction.DENY


def test_yolo_no_sandbox_deny(win_policy_yolo_no_sandbox):
    """#8 YOLO + 沙盒不可用 → DENY"""
    decision = win_policy_yolo_no_sandbox.evaluate("dir")
    assert decision.action == CommandAction.DENY


def test_dir_pipe_findstr(win_policy_auto_sandbox):
    """#2b AUTO dir | findstr → registry 认得 → READ_ONLY"""
    decision = win_policy_auto_sandbox.evaluate("dir | findstr foo")
    assert decision.action != CommandAction.DENY


def test_sandbox_fallback_whitelist_active(win_policy_auto_no_sandbox):
    """#11 沙盒不可用降级 → 白名单恢复"""
    decision = win_policy_auto_no_sandbox.evaluate("git status && dir")
    # dir 在无沙盒时被白名单拦截
    assert decision.action == CommandAction.DENY


def test_seatbelt_landlock_unchanged():
    """macOS/Linux 现有测试不受影响：run_command/run_shell_command 返回 None"""
    from app.security.sandbox.seatbelt import SeatbeltSandbox
    sb = SeatbeltSandbox()
    assert sb.run_command(["echo", "hi"], cwd="/tmp") is None
    assert sb.run_shell_command("echo hi", cwd="/tmp") is None

    from app.security.sandbox.landlock import LandlockSandbox
    lb = LandlockSandbox()
    assert lb.run_command(["echo", "hi"], cwd="/tmp") is None
    assert lb.run_shell_command("echo hi", cwd="/tmp") is None
