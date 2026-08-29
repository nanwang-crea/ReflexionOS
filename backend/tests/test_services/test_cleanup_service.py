import pytest
from datetime import datetime, timedelta
import os

from app.services.cleanup_service import CleanupService


@pytest.fixture
def temp_upload_dir(tmp_path):
    """创建临时上传目录"""
    upload_dir = tmp_path / "storage" / "uploads"
    upload_dir.mkdir(parents=True)
    return upload_dir


def test_cleanup_old_files(temp_upload_dir):
    """测试清理过期文件"""
    # 创建测试文件
    session_dir = temp_upload_dir / "test-session"
    session_dir.mkdir()

    # 旧文件（2天前）
    old_file = session_dir / "old.png"
    old_file.write_text("old")
    old_time = (datetime.now() - timedelta(days=2)).timestamp()
    os.utime(old_file, (old_time, old_time))

    # 新文件（现在）
    new_file = session_dir / "new.png"
    new_file.write_text("new")

    # 执行清理
    service = CleanupService(upload_root=str(temp_upload_dir))
    deleted = service.cleanup_old_uploads_sync(max_age_days=1)

    # 验证
    assert deleted == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_empty_directories(temp_upload_dir):
    """测试清理空目录"""
    empty_dir = temp_upload_dir / "empty-session"
    empty_dir.mkdir()

    service = CleanupService(upload_root=str(temp_upload_dir))
    service.cleanup_old_uploads_sync(max_age_days=1)

    assert not empty_dir.exists()
