from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from app.storage.models import Base
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite 数据库管理"""
    
    def __init__(self, db_path: Optional[str] = None):
        candidate_paths = [Path(db_path)] if db_path else [
            Path.home() / ".reflexion" / "reflexion.db",
            Path.cwd() / ".reflexion" / "reflexion.db",
        ]

        last_error: Optional[Exception] = None

        for candidate in candidate_paths:
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                engine = create_engine(
                    f"sqlite:///{candidate}",
                    echo=False,
                    connect_args={"check_same_thread": False}
                )

                self.db_path = str(candidate)
                self.engine = engine
                self._reset_legacy_schema_if_needed()
                Base.metadata.create_all(self.engine)

                self.SessionLocal = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=self.engine
                )

                logger.info(f"数据库初始化完成: {candidate}")
                return
            except OperationalError as exc:
                last_error = exc
                logger.warning("数据库路径不可用，尝试下一个候选路径: %s", candidate)

        if last_error is not None:
            raise last_error

    def _reset_legacy_schema_if_needed(self) -> None:
        inspector = inspect(self.engine)
        if "executions" not in inspector.get_table_names():
            return

        columns = {column["name"] for column in inspector.get_columns("executions")}
        execution_schema_ok = "project_path" in columns and "session_id" in columns

        conversation_schema_ok = True
        if "conversations" in inspector.get_table_names():
            conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
            conversation_schema_ok = {
                "item_type",
                "receipt_status",
                "details_json",
                "sequence",
            }.issubset(conversation_columns)

        if execution_schema_ok and conversation_schema_ok:
            return

        logger.warning("检测到旧版执行表结构，重建数据库以切换到新项目执行模型")
        try:
            Base.metadata.drop_all(self.engine)
        except OperationalError:
            logger.warning("旧版数据库当前不可写，跳过自动重建，等待显式清理后再初始化")
    
    @contextmanager
    def get_session(self) -> Session:
        """获取数据库会话 (上下文管理器)"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def create_session(self) -> Session:
        """创建数据库会话"""
        return self.SessionLocal()


# 全局数据库实例
db = Database()
