import logging
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import MetaData, create_engine, event, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.storage.models import Base

logger = logging.getLogger(__name__)

SESSION_CASCADE_TABLES = (
    "turns",
    "runs",
    "messages",
    "conversation_events",
)


class Database:
    """SQLite 数据库管理"""
    
    def __init__(self, db_path: str | None = None):
        candidate_paths = [Path(db_path)] if db_path else [
            Path.home() / ".reflexion" / "reflexion.db",
            Path.cwd() / ".reflexion" / "reflexion.db",
        ]

        last_error: Exception | None = None

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
                self._configure_sqlite()
                self._reset_legacy_schema_if_needed()
                self._migrate_session_cascade_schema_if_needed()
                Base.metadata.create_all(self.engine)

                self.SessionLocal = sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=self.engine
                )

                logger.info("数据库初始化完成: %s", candidate)
                return
            except OperationalError as exc:
                last_error = exc
                logger.warning("数据库路径不可用，尝试下一个候选路径: %s", candidate)

        if last_error is not None:
            raise last_error

    def _configure_sqlite(self) -> None:
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def _reset_legacy_schema_if_needed(self) -> None:
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        if "executions" not in table_names and "conversations" not in table_names:
            return

        logger.warning("检测到旧版 conversation schema，重建数据库以切换到新会话模型")
        try:
            metadata = MetaData()
            metadata.reflect(bind=self.engine)
            metadata.drop_all(bind=self.engine)
        except OperationalError:
            logger.warning("旧版数据库当前不可写，跳过自动重建，等待显式清理后再初始化")

    def _migrate_session_cascade_schema_if_needed(self) -> None:
        inspector = inspect(self.engine)
        existing_tables = set(inspector.get_table_names())
        tables_to_rebuild = [
            table_name
            for table_name in SESSION_CASCADE_TABLES
            if table_name in existing_tables and not self._has_session_cascade_fk(table_name)
        ]
        if not tables_to_rebuild:
            return

        logger.warning("检测到缺少 session 级联外键的 conversation schema，执行原地迁移")
        self._rebuild_tables_with_session_cascade(tables_to_rebuild)

    def _has_session_cascade_fk(self, table_name: str) -> bool:
        with self.engine.connect() as connection:
            foreign_keys = connection.exec_driver_sql(
                f'PRAGMA foreign_key_list("{table_name}")'
            ).mappings().all()
        return any(
            foreign_key["table"] == "sessions"
            and foreign_key["from"] == "session_id"
            and str(foreign_key["on_delete"]).upper() == "CASCADE"
            for foreign_key in foreign_keys
        )

    def _rebuild_tables_with_session_cascade(self, table_names: list[str]) -> None:
        with self.engine.begin() as connection:
            for table_name in table_names:
                legacy_table_name = f"{table_name}__legacy_no_session_fk"
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table_name}" RENAME TO "{legacy_table_name}"'
                )
                Base.metadata.tables[table_name].create(bind=connection)

                column_names = [column.name for column in Base.metadata.tables[table_name].columns]
                quoted_columns = ", ".join(f'"{column_name}"' for column_name in column_names)
                connection.exec_driver_sql(
                    f'''
                    INSERT INTO "{table_name}" ({quoted_columns})
                    SELECT {quoted_columns} FROM "{legacy_table_name}"
                    '''
                )
                connection.exec_driver_sql(f'DROP TABLE "{legacy_table_name}"')

            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            if violations:
                raise RuntimeError(
                    f"session cascade schema migration left FK violations: {violations}"
                )
    
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
