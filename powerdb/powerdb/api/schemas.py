"""内部云 REST 接口的请求体模型（Pydantic 边界校验）。

这些模型是「接口契约」：外部（测试脚本 / 前端 / 同事脚本）按这些字段提交，
服务端据此校验后再写入数据库，避免脏数据进库。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None


class SampleIn(BaseModel):
    project_id: int
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    model: Optional[str] = None
    spec_sn: Optional[str] = None
    manufacturer: Optional[str] = None


class StandardIn(BaseModel):
    code: str
    name: str
    category: Optional[str] = None
    version: Optional[str] = None


class StandardItemIn(BaseModel):
    code: str
    name: str
    unit: Optional[str] = None
    limit_min: Optional[float] = None
    limit_max: Optional[float] = None


class MeasurementIn(BaseModel):
    metric: str = Field(min_length=1, max_length=128)
    value: Optional[float] = None
    unit: Optional[str] = None
    text_value: Optional[str] = None


class RecordIn(BaseModel):
    standard_item_id: int
    status: str = "pending"
    measurements: list[MeasurementIn] = Field(default_factory=list)


class RunIn(BaseModel):
    sample_id: int
    run_no: str = Field(min_length=1, max_length=64)
    operator: Optional[str] = None
    started_at: Optional[datetime] = None
    environment: Optional[dict] = None
    remark: Optional[str] = None
    records: list[RecordIn] = Field(default_factory=list)