"""仪器仪表。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from powerdb.core.base import Base
from powerdb.models.common import JSONType, TimestampMixin


class Instrument(Base, TimestampMixin):
    """仪器仪表（功率分析仪、示波器、电子负载等）。"""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(128))        # 型号
    serial_number: Mapped[Optional[str]] = mapped_column(String(128))  # 序列号
    # 连接信息（地址/端口/协议等）用 JSON 存，便于不同仪器类型自由扩展
    connection: Mapped[Optional[dict]] = mapped_column(JSONType)