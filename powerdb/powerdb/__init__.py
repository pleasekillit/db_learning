"""powerdb：电力电子测试架构的数据库管理模块。

分层结构：
    core         -> model  ->  repository  ->  service  ->  调用方
    (引擎/会话)     (表)      (数据访问)      (业务逻辑)    (Pytest/看板/AI)

跨层还有 schemas(Pydantic) 负责边界校验与序列化。
"""
from powerdb.config import DatabaseConfig
from powerdb.core.engine import create_schema, get_engine, init_engine, session_scope

__all__ = [
    "DatabaseConfig",
    "create_schema",
    "get_engine",
    "init_engine",
    "session_scope",
]

__version__ = "0.1.0"