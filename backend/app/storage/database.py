# 数据库连接与生命周期管理模块
# 负责 SQLite 引擎创建、Alembic 增量迁移驱动、旧版 schema 兼容迁移（备份重建/补列/外键级联重建），
# 并对外提供 Session 上下文管理器（Database.get_session）。

import logging
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from alembic.config import Config as AlembicConfig
from app.storage.models import Base

logger = logging.getLogger(__name__)

# 需要保证与 sessions 表存在级联删除外键（ON DELETE CASCADE）的表名列表，
# 用于 _migrate_session_cascade_schema_if_needed 检测并原地重建 schema
SESSION_CASCADE_TABLES = (
    "turns",
    "runs",
    "messages",
    "message_search_documents",
    "conversation_events",
)


class Database:
    """SQLite 数据库管理"""

    def __init__(self, db_path: str | None = None):
        """初始化数据库连接。

        入参：
          db_path - 指定的数据库文件路径；为 None 时按顺序尝试
            ~/.reflexion/reflexion.db 和 ./.reflexion/reflexion.db 两个候选路径。
        功能/工作流程：
          依次尝试候选路径，对每个路径创建 SQLite engine，
          配置 PRAGMA、处理旧版 schema、跑 Alembic 迁移、补齐历史列/外键，
          全部成功后创建 SessionLocal 工厂；某个路径失败（OperationalError）则换下一个候选路径。
        出参：无返回值（构造函数），成功后在 self 上设置 db_path/engine/SessionLocal；
          若所有候选路径都失败，抛出最后一次捕获到的异常。
        """
        candidate_paths = (
            [Path(db_path)]
            if db_path
            else [
                Path.home() / ".reflexion" / "reflexion.db",
                Path.cwd() / ".reflexion" / "reflexion.db",
            ]
        )

        last_error: Exception | None = None

        for candidate in candidate_paths:
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                engine = create_engine(
                    f"sqlite:///{candidate}", echo=False, connect_args={"check_same_thread": False}
                )

                self.db_path = str(candidate)
                self.engine = engine
                self._configure_sqlite()
                self._handle_legacy_schema_if_needed()
                self._run_alembic_migrations()
                self._migrate_session_mode_columns_if_needed()
                self._migrate_session_cascade_schema_if_needed()

                self.SessionLocal = sessionmaker(
                    autocommit=False, autoflush=False, bind=self.engine
                )

                logger.info("数据库初始化完成: %s", candidate)
                return
            except OperationalError as exc:
                last_error = exc
                logger.warning("数据库路径不可用，尝试下一个候选路径: %s", candidate)

        if last_error is not None:
            raise last_error

    def _configure_sqlite(self) -> None:
        """为 SQLite 连接注册事件监听：每次新建连接时开启外键约束（PRAGMA foreign_keys=ON）。

        入参：无（使用 self.engine）
        功能：SQLite 默认不强制外键约束，这里通过 connect 事件确保每条连接都开启，
          保证 ON DELETE CASCADE 等外键行为生效。
        出参：无返回值
        """

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def _handle_legacy_schema_if_needed(self) -> None:
        """检测并处理旧版不兼容 schema：备份后重建，避免静默丢数据。

        入参：无（使用 self.engine / self.db_path）
        功能/工作流程：
          1. 检查是否存在旧表 executions/conversations，或 messages 表缺少
             turn_message_index 相关唯一索引 —— 命中任一条件即判定为不兼容 schema。
          2. 命中则先把数据库文件备份为 *.db.legacy_backup（已存在则跳过备份）。
          3. 反射当前 schema 并 drop 所有表，交由后续 _run_alembic_migrations 重建。
        出参：无返回值；不兼容则直接原地清空表结构（数据已提前备份到文件）。
        """
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())

        reset_reason: str | None = None
        if "executions" in table_names or "conversations" in table_names:
            reset_reason = "检测到旧版 conversation schema，需要重建数据库以切换到新会话模型"
        elif "messages" in table_names and not self._has_turn_message_index_schema():
            reset_reason = "检测到不兼容的 messages schema，需要重建数据库以切换到 turn_message_index"

        if reset_reason is None:
            return

        logger.warning(reset_reason)

        # 备份旧数据库文件，防止数据静默丢失
        db_path = Path(self.db_path)
        backup_path = db_path.with_suffix(".db.legacy_backup")
        if not backup_path.exists():
            import shutil

            shutil.copy2(db_path, backup_path)
            logger.info("旧版数据库已备份至: %s", backup_path)
        else:
            logger.info("备份文件已存在，跳过备份: %s", backup_path)

        # 重建 schema
        try:
            from sqlalchemy import MetaData

            metadata = MetaData()
            metadata.reflect(bind=self.engine)
            metadata.drop_all(bind=self.engine)
        except OperationalError:
            logger.warning("旧版数据库当前不可写，跳过自动重建，等待显式清理后再初始化")

    def _run_alembic_migrations(self) -> None:
        """运行 Alembic 增量迁移，替代 Base.metadata.create_all 的粗暴方式。

        入参：无（使用 self.engine / self.db_path）
        功能/工作流程：
          1. 若项目未配置 alembic.ini，直接用 create_all 建表（兼容无迁移环境）。
          2. 否则加载 alembic 配置并绑定当前数据库 URL；
             若数据库已有表但没有 alembic_version 记录（老库），先 stamp 到
             initial_schema 版本号，避免重复建表报错。
          3. 执行 command.upgrade 到 head，应用所有未执行的迁移脚本。
          4. 迁移失败则记录警告并回退到 create_all。
          5. 迁移过程中 Alembic 会篡改 root logger 的 handlers，
             这里在 try/finally 中保存并恢复原有的日志 handler 配置，避免日志丢失。
        出参：无返回值；直接修改数据库 schema 到最新版本。
        """
        alembic_cfg_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
        if not alembic_cfg_path.exists():
            logger.info("未找到 alembic.ini，使用 create_all 初始化表结构")
            Base.metadata.create_all(self.engine)
            return

        alembic_cfg = AlembicConfig(str(alembic_cfg_path))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

        # Alembic 迁移时会临时修改 root logger 的 handlers，
        # 保存/恢复时需保留我们配置的文件日志 handler，避免日志丢失
        root_logger = logging.getLogger()
        saved_level = root_logger.level
        saved_handlers = list(root_logger.handlers)

        try:
            inspector = inspect(self.engine)
            table_names = inspector.get_table_names()
            has_alembic_version = "alembic_version" in table_names
            has_version_record = False
            if has_alembic_version:
                with self.engine.connect() as conn:
                    result = conn.execute(text("SELECT version_num FROM alembic_version"))
                    has_version_record = result.fetchone() is not None

            if table_names and not has_version_record:
                command.stamp(alembic_cfg, "d3185a24f1c8")
                logger.info("旧数据库已标记为 Alembic initial_schema 版本")

            command.upgrade(alembic_cfg, "head")
        except Exception as exc:
            logger.warning("Alembic 迁移失败，回退到 create_all: %s", exc)
            Base.metadata.create_all(self.engine)
        finally:
            # 恢复 Alembic 迁移前的日志 handler 配置
            # 先移除 Alembic 添加的 handler，再恢复原始 handler
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
            for handler in saved_handlers:
                root_logger.addHandler(handler)
            root_logger.setLevel(saved_level)

    def _has_turn_message_index_schema(self) -> bool:
        """检查 messages 表是否已是新版 turn_message_index schema。

        入参：无（使用 self.engine）
        功能：读取 messages 表列信息，确认存在 turn_message_index 列；
          再读取表的唯一索引，确认存在覆盖 (turn_id, turn_message_index) 的唯一约束。
        出参：bool —— True 表示 schema 已是新版（含该唯一约束），否则 False（需要重建）。
        """
        with self.engine.connect() as connection:
            message_columns = {
                row["name"]
                for row in connection.exec_driver_sql('PRAGMA table_info("messages")')
                .mappings()
                .all()
            }
            if "turn_message_index" not in message_columns:
                return False

            unique_index_names = [
                row["name"]
                for row in connection.exec_driver_sql('PRAGMA index_list("messages")')
                .mappings()
                .all()
                if row["unique"]
            ]

            unique_index_columns = {
                tuple(
                    index_row["name"]
                    for index_row in connection.exec_driver_sql(
                        f'PRAGMA index_info("{index_name}")'
                    )
                    .mappings()
                    .all()
                )
                for index_name in unique_index_names
            }

        return ("turn_id", "turn_message_index") in unique_index_columns

    def _migrate_session_mode_columns_if_needed(self) -> None:
        """补齐历史数据库缺失的会话模式列。

        函数名：_migrate_session_mode_columns_if_needed
        入参：无
        功能：在 Alembic 版本表与本地迁移文件不一致时，兜底补齐 sessions 表新增列。
        运行逻辑：
          1. 检查 sessions 表是否存在，避免新库初始化前误操作。
          2. 读取当前列集合，仅对缺失的 agent_mode / permission_mode 执行 ALTER TABLE。
          3. 使用 DEFAULT + NOT NULL，保证历史会话可直接映射到 ORM 模型。
        出参：None - 直接修改当前数据库 schema
        """
        inspector = inspect(self.engine)
        if "sessions" not in inspector.get_table_names():
            return

        session_columns = {column["name"] for column in inspector.get_columns("sessions")}
        statements: list[str] = []
        if "agent_mode" not in session_columns:
            statements.append(
                "ALTER TABLE sessions ADD COLUMN agent_mode VARCHAR NOT NULL DEFAULT 'build'"
            )
        if "permission_mode" not in session_columns:
            statements.append(
                "ALTER TABLE sessions ADD COLUMN permission_mode VARCHAR NOT NULL DEFAULT 'auto'"
            )

        if not statements:
            return

        logger.warning("检测到 sessions 表缺少模式列，执行兼容迁移: %s", statements)
        with self.engine.begin() as connection:
            for statement in statements:
                connection.exec_driver_sql(statement)

    def _migrate_session_cascade_schema_if_needed(self) -> None:
        """检测并修复缺失 session 级联外键的历史 schema。

        入参：无（使用 self.engine）
        功能/工作流程：
          遍历 SESSION_CASCADE_TABLES 中已存在的表，用 _has_session_cascade_fk 逐个检测
          是否具备指向 sessions.id 且 ON DELETE CASCADE 的外键；
          缺失的表收集后交给 _rebuild_tables_with_session_cascade 原地重建。
        出参：无返回值；无需迁移的表不受影响。
        """
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
        """检查指定表是否已具备指向 sessions.id 的级联删除外键。

        入参：table_name - 要检查的表名
        功能：通过 PRAGMA foreign_key_list 读取该表全部外键定义，
          判断是否存在 from=session_id、指向 sessions 表、且 on_delete=CASCADE 的外键。
        出参：bool —— True 表示已具备级联外键，False 表示需要迁移重建。
        """
        with self.engine.connect() as connection:
            foreign_keys = (
                connection.exec_driver_sql(f'PRAGMA foreign_key_list("{table_name}")')
                .mappings()
                .all()
            )
        return any(
            foreign_key["table"] == "sessions"
            and foreign_key["from"] == "session_id"
            and str(foreign_key["on_delete"]).upper() == "CASCADE"
            for foreign_key in foreign_keys
        )

    def _rebuild_tables_with_session_cascade(self, table_names: list[str]) -> None:
        """原地重建表结构以补齐 session 级联外键（SQLite 不支持直接 ALTER 外键）。

        入参：table_names - 需要重建的表名列表
        功能/工作流程：
          对每张表：先把旧表 RENAME 为 "{table}__legacy_no_session_fk"，
          再按 ORM 中最新的表定义（Base.metadata.tables[table_name]）创建新表，
          将旧表数据按列名整列 INSERT 迁移过去，最后 DROP 掉旧表。
          全部表处理完后执行 PRAGMA foreign_key_check，若发现外键违规则抛出 RuntimeError 回滚整个事务。
        出参：无返回值；成功则新表已具备级联外键且数据保留，失败则抛异常并回滚。
        """
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
        """获取数据库会话（上下文管理器）。

        入参：无
        功能：从 SessionLocal 工厂创建一个新 Session；with 块内代码正常结束则自动 commit，
          抛出异常则 rollback 并向外重新抛出；无论成功失败最终都会 close 会话。
        出参：yield 一个 sqlalchemy.orm.Session 供 with 块内使用。
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# 全局数据库实例（延迟初始化）
# 使用 PEP 562 __getattr__ 实现懒加载，测试时可通过 _db 注入 mock
_db = None


def __getattr__(name):
    global _db
    if name == "db":
        if _db is None:
            _db = Database()
        return _db
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
