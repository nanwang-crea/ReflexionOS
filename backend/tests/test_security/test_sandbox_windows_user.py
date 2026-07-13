# Elevated 档沙盒用户管理单测（mock subprocess，无需管理员权限 / 真实 Windows）
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_pywin32():
    """Mock pywin32 模块，避免非 Windows 上 get_user_token 的 import 失败"""
    if sys.platform != "win32":
        with patch.dict("sys.modules", {
            "win32security": MagicMock(),
            "win32con": MagicMock(),
            "pywintypes": MagicMock(),
        }):
            yield
    else:
        yield


@pytest.fixture(autouse=True)
def mock_subprocess():
    """默认 mock subprocess.run 返回 returncode=0（成功）"""
    with patch("app.security.sandbox.windows_user.subprocess.run") as mock_run:
        result = MagicMock()
        result.returncode = 0
        mock_run.return_value = result
        yield mock_run


def test_ensure_sandbox_users_creates_both():
    """ensure_sandbox_users 应创建 Offline 和 Online 两个用户"""
    from app.security.sandbox.windows_user import ensure_sandbox_users

    with patch("app.security.sandbox.windows_user.sys.platform", "win32"):
        result = ensure_sandbox_users()
        assert result is True


def test_ensure_sandbox_users_calls_net_user():
    """ensure_sandbox_users 应调用 net user 两次"""
    from app.security.sandbox.windows_user import ensure_sandbox_users

    with patch("app.security.sandbox.windows_user.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_user.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            ensure_sandbox_users()
            assert mock_run.call_count == 2


def test_ensure_sandbox_users_fails_on_nonzero_returncode():
    """subprocess.run 返回非零退出码时应返回 False"""
    from app.security.sandbox.windows_user import ensure_sandbox_users

    with patch("app.security.sandbox.windows_user.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_user.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = ensure_sandbox_users()
            assert result is False


def test_ensure_sandbox_users_non_windows():
    """非 Windows 平台应返回 False"""
    from app.security.sandbox.windows_user import ensure_sandbox_users

    with patch("app.security.sandbox.windows_user.sys.platform", "linux"):
        assert ensure_sandbox_users() is False


def test_get_user_token_calls_logon_user():
    """get_user_token 应调用 LogonUser（使用 LOGON32_LOGON_BATCH）"""
    from app.security.sandbox.windows_user import get_user_token, OFFLINE_USER

    with patch("app.security.sandbox.windows_user.sys.platform", "win32"):
        with patch.dict("sys.modules", {
            "win32security": MagicMock(),
            "win32con": MagicMock(),
        }):
            import win32con as mock_con
            import win32security as mock_sec
            mock_sec.LogonUser.return_value = 12345
            token = get_user_token(OFFLINE_USER)
            assert token is not None
            mock_sec.LogonUser.assert_called_once()
            # 验证使用的是 LOGON32_LOGON_BATCH（值应为 3）
            logon_type_arg = mock_sec.LogonUser.call_args[0][3]
            assert logon_type_arg == mock_con.LOGON32_LOGON_BATCH or logon_type_arg == 3


def test_remove_sandbox_users_deletes_both():
    """remove_sandbox_users 应删除两个用户"""
    from app.security.sandbox.windows_user import remove_sandbox_users

    with patch("app.security.sandbox.windows_user.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_user.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = remove_sandbox_users()
            assert result is True
            assert mock_run.call_count == 2


def test_remove_sandbox_users_fails_on_nonzero():
    """删除用户返回非零退出码时应返回 False"""
    from app.security.sandbox.windows_user import remove_sandbox_users

    with patch("app.security.sandbox.windows_user.sys.platform", "win32"):
        with patch("app.security.sandbox.windows_user.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            result = remove_sandbox_users()
            assert result is False
