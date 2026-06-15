import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class CleanupService:
    """图片上传文件清理服务"""

    def __init__(self, upload_root: str = "storage/uploads"):
        self.upload_root = Path(upload_root)

    def cleanup_old_uploads_sync(self, max_age_days: int = 1) -> int:
        """同步清理超过指定天数的上传文件

        Args:
            max_age_days: 最大保留天数

        Returns:
            删除的文件数量
        """
        if not self.upload_root.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=max_age_days)
        deleted_count = 0

        for session_dir in self.upload_root.iterdir():
            if not session_dir.is_dir():
                continue

            for file_path in session_dir.iterdir():
                if not file_path.is_file():
                    continue

                # 检查文件修改时间
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"删除过期文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"删除文件失败 {file_path}: {e}")

            # 删除空目录
            try:
                if not any(session_dir.iterdir()):
                    session_dir.rmdir()
                    logger.debug(f"删除空目录: {session_dir}")
            except Exception:
                pass

        if deleted_count > 0:
            logger.info(f"清理过期上传文件: {deleted_count} 个")

        return deleted_count
