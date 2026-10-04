"""测量结果的边界模型（入参校验 + 出参序列化）。

用于保证「看板 / AI / API」拿到的结构稳定，以及写入前对入参做校验。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MeasurementCreate(BaseModel):
    """写入一个标量测量结果时的入参。"""

    test_record_id: int
    metric: str = Field(min_length=1, max_length=128)
    value: Optional[float] = None
    unit: Optional[str] = None
    text_value: Optional[str] = None
    extra: Optional[dict] = None


class MeasurementOut(BaseModel):
    """对外输出的测量结果（可用于看板 / AI 接口）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    metric: str
    value: Optional[float]
    unit: Optional[str]
    text_value: Optional[str]
    created_at: datetime


class ComparisonRow(BaseModel):
    """历史横向对比的一行结果。"""

    sample_code: str
    run_no: str
    item_name: str
    value: Optional[float]
    unit: Optional[str]
    started_at: Optional[datetime]