"""数据库引擎与会话管理。

作用：全局唯一 engine + Session 工厂，以及 `session_scope` 事务上下文：
    - 正常退出自动 commit；
    - 抛出异常自动 rollback；
    - 无论怎样都会 close。

业务代码只通过 `session_scope` 拿到会话，绝不手动管理连接，
从而把「事务边界」统一收口到这一处。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from powerdb.config import DatabaseConfig

_engine: Engine | None = None
_SessionFactory: Any = None


def _build_engine(config: DatabaseConfig) -> Engine:
    connect_args: dict[str, Any] = {}
    if config.url.startswith("sqlite"):
        # SQLite 文件被多个连接跨线程访问时需要关闭该检查
        connect_args["check_same_thread"] = False

    return create_engine(
        config.url,
        echo=config.echo,
        pool_size=config.pool_size,
        pool_recycle=config.pool_recycle,
        connect_args=connect_args,
        future=True,
    )


def init_engine(config: DatabaseConfig | None = None) -> Engine:
    """初始化全局引擎（应用启动时调用一次）。"""
    global _engine, _SessionFactory
    config = config or DatabaseConfig()
    _engine = _build_engine(config)

    if config.url.startswith("sqlite"):
        # 让 SQLite 也遵守外键约束（默认是关闭的）
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, _: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def _get_session_factory() -> Any:
    if _SessionFactory is None:
        init_engine()
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务性会话上下文：进入拿会话，退出提交，异常回滚。"""
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_schema(drop: bool = False) -> None:
    """创建（或重建）所有表。

    用于 SQLite 快速起步；一旦引入 Alembic（阶段4+），生产环境请改用迁移，
    不再依赖本函数来演进结构。
    """
    from powerdb import models  # noqa: F401  导入以注册所有模型到 metadata
    from powerdb.core.base import Base

    engine = get_engine()
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)