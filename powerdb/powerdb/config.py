"""数据库配置。

所有连接相关配置集中在这里，业务代码绝不写死数据库地址 / 账号，
而是从这里（或环境变量 POWERDB_URL）读取，从而做到：
    「本地 SQLite 起步」 -> 「集中 PostgreSQL」只改连接串、不改业务代码。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# 默认 SQLite 文件落在项目根目录下
_DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent / "powerdb.db")


@dataclass
class DatabaseConfig:
    """数据库连接与引擎参数。"""

    # 连接串。默认本地 SQLite；进阶时换个环境变量即可切 PostgreSQL：
    #   export POWERDB_URL="postgresql+psycopg://user:pass@127.0.0.1:5432/powerdb"
    url: str = field(
        default_factory=lambda: os.environ.get(
            "POWERDB_URL", f"sqlite:///{_DEFAULT_DB_PATH}"
        )
    )

    echo: bool = field(
        default_factory=lambda: os.environ.get("POWERDB_ECHO", "0") == "1"
    )  # 是否打印 SQL（调试用）

    pool_size: int = 5        # 连接池大小（SQLite 下被忽略，PG 并发有意义）
    pool_recycle: int = 3600  # 连接回收秒数（PG 长连接防失效）