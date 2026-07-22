# Elevated 档防火墙策略单测（mock subprocess，无需管理员权限 / 真实 Windows）
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_result():
    """返回 returncode=0 的 subprocess 结果"""
    r = MagicMock()
    r.returncode = 0
    return r


def test_block_outbound_for_user_non_windows():
    """非 Windows 平台应返回 False"""
    from app.security.sandbox.windows_firewall import block_outbound_for_user

    with patch("app.security.sandbox.windows_firewall.sys.platform", "linux"):
        assert block_outbound_for_user("TestUser") is False


def test_block_outbound_uses_netsh():
    """block_outbound_for_user 应调用 netsh 添加阻止规则"""
    from app.security.sandbox.windows_firewall import block_outbound_for_user

    with patch("app.security.sandbox.windows_firewall.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_firewall.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = block_outbound_for_user("ReflexionSandboxOffline")
            assert result is True
            args = mock_run.call_args[0][0]
            assert "netsh" in args[0]
            assert "BlockOutbound_ReflexionSandboxOffline" in str(args)
            assert "action=block" in str(args)


def test_block_outbound_fails_on_nonzero_returncode():
    """netsh 返回非零退出码时应返回 False"""
    from app.security.sandbox.windows_firewall import block_outbound_for_user

    with patch("app.security.sandbox.windows_firewall.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_firewall.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = block_outbound_for_user("TestUser")
            assert result is False


def test_allow_outbound_for_user_uses_remoteport():
    """allow_outbound_for_user 应使用 remoteport（不是 localport）"""
    from app.security.sandbox.windows_firewall import allow_outbound_for_user

    with patch("app.security.sandbox.windows_firewall.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_firewall.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = allow_outbound_for_user("ReflexionSandboxOnline", ports=[443, 80])
            assert result is True
            args = mock_run.call_args[0][0]
            assert "AllowOutbound_ReflexionSandboxOnline" in str(args)
            assert "action=allow" in str(args)
            assert "remoteport=443,80" in str(args), "应用 remoteport 而非 localport"
            assert "localport" not in str(args)


def test_allow_outbound_default_port_443():
    """allow_outbound_for_user 默认仅允许 443 端口"""
    from app.security.sandbox.windows_firewall import allow_outbound_for_user

    with patch("app.security.sandbox.windows_firewall.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_firewall.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            allow_outbound_for_user("TestUser")
            args = mock_run.call_args[0][0]
            assert "remoteport=443" in str(args)


def test_allow_outbound_fails_on_nonzero_returncode():
    """netsh 返回非零退出码时应返回 False"""
    from app.security.sandbox.windows_firewall import allow_outbound_for_user

    with patch("app.security.sandbox.windows_firewall.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_firewall.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = allow_outbound_for_user("TestUser")
            assert result is False


def test_remove_rules_for_user():
    """remove_rules_for_user 应删除 Block 和 Allow 两条规则"""
    from app.security.sandbox.windows_firewall import remove_rules_for_user

    with patch("app.security.sandbox.windows_firewall.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_firewall.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = remove_rules_for_user("TestUser")
            assert result is True
            assert mock_run.call_count == 2
