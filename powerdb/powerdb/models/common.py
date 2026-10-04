"""通用字段与类型，供各模型复用。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# 通用 JSON 类型：SQLite 落成 TEXT，PostgreSQL 自动升级为 JSONB。
# 这样业务代码里统一写 JSONType，换库不感知方言差异。
JSONType = JSON().with_variant(JSONB(), "postgresql")


class TimestampMixin:
    """创建 / 更新时间戳，所有业务表统一附带，便于追溯与看板按时间筛选。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )