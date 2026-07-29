# Windows 文件 ACL 写入边界单测
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="requires Windows APIs")


@pytest.fixture(autouse=True)
def mock_pywin32():
    if sys.platform != "win32":
        with patch.dict("sys.modules", {
            "win32security": MagicMock(),
            "win32con": MagicMock(),
            "win32file": MagicMock(),
            "win32api": MagicMock(),
            "pywintypes": MagicMock(),
            "ntsecuritycon": MagicMock(),
        }):
            yield
    else:
        yield


def test_apply_write_boundary_creates_acls():
    """ACL 应在沙箱目录设置 ALLOW ACE"""
    from app.security.sandbox.windows_acl import apply_write_boundary

    with tempfile.TemporaryDirectory() as tmpdir:
        result = apply_write_boundary(tmpdir, allowed_write_dirs=[tmpdir])
        assert result is True


def test_apply_write_boundary_fails_on_invalid_dir():
    """ACL 在不存在的目录上应返回 False"""
    from app.security.sandbox.windows_acl import apply_write_boundary

    result = apply_write_boundary(r"C:\nonexistent_sandbox_12345", allowed_write_dirs=[r"C:\nonexistent_sandbox_12345"])
    assert result is False


def test_apply_write_boundary_skips_missing_dirs():
    """允许列表中部分目录不存在时，应跳过缺失目录并对存在目录成功设置 ACL。

    复现日志中的真实场景：allowed_paths 里包含未安装的 skills 目录，
    不应因为该目录缺失而让整条命令的 ACL 设置失败。
    """
    from app.security.sandbox.windows_acl import apply_write_boundary

    with tempfile.TemporaryDirectory() as tmpdir:
        missing_dir = os.path.join(tmpdir, "not_existed_skills")
        result = apply_write_boundary(tmpdir, allowed_write_dirs=[tmpdir, missing_dir])
        assert result is True


def test_create_sandbox_work_dir():
    """沙盒工作目录创建和清理"""
    from app.security.sandbox.windows_acl import cleanup_sandbox_work_dir, create_sandbox_work_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox_dir = create_sandbox_work_dir(tmpdir)
        assert os.path.isdir(sandbox_dir), "沙盒目录应被创建"
        cleanup_sandbox_work_dir(sandbox_dir)
        assert not os.path.isdir(sandbox_dir), "清理后目录应被删除"
