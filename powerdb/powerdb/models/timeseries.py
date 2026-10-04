"""时序数据。

存储策略（混合三层）：
    1. 通道元数据 -> timeseries_channels；
    2. 高频原始波形 -> 文件（Parquet/NPY/HDF5），路径回写 raw_path；
    3. 中低频 / 降采样点 -> timeseries_points 长表，供 SQL 聚合与看板趋势。

高频原始波形不要逐点进关系表（体积大、写入慢），只索引到文件。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from powerdb.core.base import Base
from powerdb.models.common import TimestampMixin


class TimeSeriesChannel(Base, TimestampMixin):
    """一条时序通道的元数据（如 Ua、Ia、P 等波形）。"""

    __tablename__ = "timeseries_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_record_id: Mapped[int] = mapped_column(ForeignKey("test_records.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)   # 通道名
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    sample_rate: Mapped[Optional[float]] = mapped_column(Float)      # 采样率 Hz
    point_count: Mapped[int] = mapped_column(Integer, default=0)
    start_time: Mapped[Optional[float]] = mapped_column(Float)       # 起始时刻（Unix 秒或相对秒）
    raw_path: Mapped[Optional[str]] = mapped_column(String(512))     # 原始波形文件路径

    test_record: Mapped["TestRecord"] = relationship(back_populates="series")
    points: Mapped[list["TimeSeriesPoint"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class TimeSeriesPoint(Base, TimestampMixin):
    """单个采样点（长表结构，适合 SQL 聚合 / 降采样 / 范围查询）。"""

    __tablename__ = "timeseries_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("timeseries_channels.id"), index=True)
    t: Mapped[float] = mapped_column(Float, nullable=False)     # 时间
    value: Mapped[float] = mapped_column(Float, nullable=False)  # 采样值

    channel: Mapped["TimeSeriesChannel"] = relationship(back_populates="points")