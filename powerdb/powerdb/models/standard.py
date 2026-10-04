"""标准（能标 / 国标 / 行标）与其测试项。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from powerdb.core.base import Base
from powerdb.models.common import TimestampMixin


class Standard(Base, TimestampMixin):
    """标准本体，如 GB/T 34120（储能逆变器）、NB/T 等能标/国标。"""

    __tablename__ = "standards"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 标准号
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(32))  # 能标 / 国标 / 行标 / 企标
    version: Mapped[Optional[str]] = mapped_column(String(32))

    items: Mapped[list["StandardItem"]] = relationship(back_populates="standard")


class StandardItem(Base, TimestampMixin):
    """标准中的测试项（如效率、温升、谐波、绝缘电阻）。"""

    __tablename__ = "standard_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    standard_id: Mapped[int] = mapped_column(ForeignKey("standards.id"), index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)   # 测试项编号
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    limit_min: Mapped[Optional[float]] = mapped_column(Float)
    limit_max: Mapped[Optional[float]] = mapped_column(Float)
    note: Mapped[Optional[str]] = mapped_column(Text)

    standard: Mapped["Standard"] = relationship(back_populates="items")