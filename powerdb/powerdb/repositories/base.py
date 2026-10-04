"""通用仓储基类。

所有数据库访问（增删改查）都被约束在仓储层：
    - Service 层只调用仓储方法，不直接碰 SQL；
    - 复杂查询（JOIN/聚合）写在具体仓储里，服务层调用语义清晰的方法名。
"""
from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from powerdb.core.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    """最常用的 CRUD 方法；具体仓储继承并按需扩展复杂查询。"""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        return obj

    def add_all(self, objs: list[ModelT]) -> None:
        self.session.add_all(objs)

    def get(self, obj_id: int) -> Optional[ModelT]:
        return self.session.get(self.model, obj_id)

    def get_by(self, **kwargs: Any) -> Optional[ModelT]:
        return self.session.scalar(select(self.model).filter_by(**kwargs))

    def list(self, limit: Optional[int] = None, **kwargs: Any) -> list[ModelT]:
        stmt = select(self.model).filter_by(**kwargs)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def delete(self, obj: ModelT) -> None:
        self.session.delete(obj)

    def count(self, **kwargs: Any) -> int:
        stmt = select(func.count()).select_from(self.model).filter_by(**kwargs)
        return self.session.scalar(stmt) or 0