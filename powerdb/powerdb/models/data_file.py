"""数据文件（用例相关的原始数据、报告、日志等）。

对应 Excel「相关数据文件」列；它的存在体现了：
    「表格设计」与「数据库设计」共用同一套字段，不割裂。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from powerdb.core.base import Base
from powerdb.models.common import TimestampMixin

class DataFile(Base, TimestampMixin):
    """与某条测试记录（用例执行）相关联的数据文件。"""

    __tablename__ = "data_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_record_id: Mapped[int] = mapped_column(ForeignKey("test_records.id"), index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)  # 文件名（给业务看）
    path: Mapped[str] = mapped_column(String(512), nullable=False)  # 实际存储路径
    kind: Mapped[Optional[str]] = mapped_column(String(32))  # raw / report / log / image
    note: Mapped[Optional[str]] = mapped_column(Text)

    test_record: Mapped["TestRecord"] = relationship(back_populates="files")