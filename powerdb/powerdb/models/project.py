"""项目与样品（被测产品 / 设备）。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from powerdb.core.base import Base
from powerdb.models.common import TimestampMixin


class Project(Base, TimestampMixin):
    """项目 / 产品线，作为样品与试验的最外层聚合单位。"""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    samples: Mapped[list["Sample"]] = relationship(back_populates="project")


class Sample(Base, TimestampMixin):
    """被测样品 / 设备（如某型号逆变器、充电桩、电源模块）。"""

    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 样品编号
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(128))   # 型号
    spec_sn: Mapped[Optional[str]] = mapped_column(String(128))  # 序列号
    manufacturer: Mapped[Optional[str]] = mapped_column(String(128))

    project: Mapped["Project"] = relationship(back_populates="samples")
    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="sample")