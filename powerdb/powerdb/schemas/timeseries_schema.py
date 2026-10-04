"""时序数据的边界模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    """创建时序通道的入参。"""

    test_record_id: int
    name: str = Field(min_length=1, max_length=128)
    unit: Optional[str] = None
    sample_rate: Optional[float] = None
    start_time: Optional[float] = None
    raw_path: Optional[str] = None