"""ORM 声明基类。

所有模型都继承 Base；Alembic 迁移也以 Base.metadata 为唯一事实来源。
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类。"""