import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.storage.models import Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False：fileConfig 默认 True 会把所有已存在的
    # logger（包括迁移前已 import 的 app.* 模块 logger）永久置为 disabled，
    # 导致迁移后这些模块的日志全部静默（生产隐患），也会让测试里 caplog
    # 断言假阴性。alembic.ini 的 [loggers] 只管理 root/sqlalchemy/alembic，
    # 无需禁用其他 logger。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Expand ~ in database URL
db_url = config.get_main_option("sqlalchemy.url")
if db_url and "~" in db_url:
    db_url = db_url.replace("~", os.path.expanduser("~"))
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
