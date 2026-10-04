"""Alembic 迁移环境。

把「结构变更」从「业务代码」里剥离出来：加列 / 加表都走 alembic，
而不是手改数据库。SQLite 与 PostgreSQL 共用这一套迁移入口。
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from powerdb import models  # noqa: F401  导入以注册所有模型
from powerdb.config import DatabaseConfig
from powerdb.core.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 统一从 DatabaseConfig 读取连接串（支持 POWERDB_URL 环境变量）
db_config = DatabaseConfig()
config.set_main_option("sqlalchemy.url", db_config.url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 而不连接数据库。"""
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
    """在线模式：连接数据库并执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite 不原生支持 ALTER，用 batch 模式重写表
            render_as_batch=db_config.url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()