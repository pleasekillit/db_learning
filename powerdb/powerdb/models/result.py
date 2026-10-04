"""标量测量结果。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from powerdb.core.base import Base
from powerdb.models.common import JSONType, TimestampMixin


class Measurement(Base, TimestampMixin):
    """一次测试记录下的单个标量指标（效率、温升、THD 等）。

    metric 用字符串而非固定列，是为了让「新增指标」无需改表，
    这是面向 AI 分析与横向对比的关键：指标名是数据，不是 schema。
    """

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_record_id: Mapped[int] = mapped_column(ForeignKey("test_records.id"), index=True)
    metric: Mapped[str] = mapped_column(String(128), nullable=False)  # 指标名，如 efficiency
    value: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    text_value: Mapped[Optional[str]] = mapped_column(Text)  # 非数值型结果
    extra: Mapped[Optional[dict]] = mapped_column(JSONType)  # 判定阈值、精度等扩展

    test_record: Mapped["TestRecord"] = relationship(back_populates="measurements")