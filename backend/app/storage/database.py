from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from pathlib import Path
from app.storage.models import Base
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite 数据库管理"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # 默认在用户目录下创建数据库
            db_dir = Path.home() / ".reflexion"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "reflexion.db")
        
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False}
        )
        
        # 创建表
        Base.metadata.create_all(self.engine)
        
        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"数据库初始化完成: {db_path}")
    
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
