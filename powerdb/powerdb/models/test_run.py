"""测试运行（一次完整试验批次）与测试记录。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from powerdb.core.base import Base
from powerdb.models.common import JSONType, TimestampMixin


class TestRun(Base, TimestampMixin):
    """一次完整试验 / 一批测试。一个样品可对应多次 TestRun。"""

    __tablename__ = "test_runs"
    __test__ = False  # 避免被 pytest 当作测试类收集

    id: Mapped[int] = mapped_column(primary_key=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), index=True)
    run_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 试验编号
    operator: Mapped[Optional[str]] = mapped_column(String(64))    # 操作员
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    environment: Mapped[Optional[dict]] = mapped_column(JSONType)  # 温湿度、气压等环境条件
    remark: Mapped[Optional[str]] = mapped_column(Text)

    sample: Mapped["Sample"] = relationship(back_populates="test_runs")
    records: Mapped[list["TestRecord"]] = relationship(
        back_populates="test_run", cascade="all, delete-orphan"
    )


class TestRecord(Base, TimestampMixin):
    """某次试验中针对某个标准测试项的一条记录（承接标量结果与时序通道）。"""

    __tablename__ = "test_records"
    __test__ = False  # 避免被 pytest 当作测试类收集

    id: Mapped[int] = mapped_column(primary_key=True)
    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"), index=True)
    standard_item_id: Mapped[int] = mapped_column(ForeignKey("standard_items.id"), index=True)
    instrument_id: Mapped[Optional[int]] = mapped_column(ForeignKey("instruments.id"))
    status: Mapped[Optional[str]] = mapped_column(String(16))  # pass / fail / pending
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    test_run: Mapped["TestRun"] = relationship(back_populates="records")
    standard_item: Mapped["StandardItem"] = relationship()
    instrument: Mapped[Optional["Instrument"]] = relationship()
    measurements: Mapped[list["Measurement"]] = relationship(
        back_populates="test_record", cascade="all, delete-orphan"
    )
    series: Mapped[list["TimeSeriesChannel"]] = relationship(
        back_populates="test_record", cascade="all, delete-orphan"
    )
    files: Mapped[list["DataFile"]] = relationship(
        back_populates="test_record", cascade="all, delete-orphan"
    )