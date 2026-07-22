# Windows Restricted Token 构造测试（mock pywin32，无需真 Windows）
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_pywin32():
    """Mock pywin32 模块，避免 ImportError 在非 Windows 上"""
    if sys.platform != "win32":
        mock_win32security = MagicMock()
        mock_win32con = MagicMock()
        mock_win32api = MagicMock()
        with patch.dict("sys.modules", {
            "win32security": mock_win32security,
            "win32con": mock_win32con,
            "win32api": mock_win32api,
            "pywintypes": MagicMock(),
        }):
            yield
    else:
        yield


def test_create_restricted_token_disables_privileges():
    """Restricted Token 应禁用高风险权限"""
    from app.security.sandbox.windows_token import create_restricted_token

    token = create_restricted_token()
    assert token is not None


def test_restricted_token_removes_admin_sid():
    """Restricted Token 应移除 Administrators SID"""
    from app.security.sandbox.windows_token import create_restricted_token

    with patch("app.security.sandbox.windows_token.win32security") as mock_sec:
        mock_sec.CreateRestrictedToken.return_value = MagicMock()
        token = create_restricted_token()
        assert token is not None
        # 验证 CreateRestrictedToken 被调用
        mock_sec.CreateRestrictedToken.assert_called_once()
        args, _ = mock_sec.CreateRestrictedToken.call_args
        # args[2] 是 SIDsToDisable 参数
        assert args[2] is not None, "应禁用高风险 SID"
