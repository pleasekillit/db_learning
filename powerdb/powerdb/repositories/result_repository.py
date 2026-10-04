"""测量结果仓储：面向「历史横向对比」的查询集中在这里。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from powerdb.models.project import Sample
from powerdb.models.result import Measurement
from powerdb.models.standard import StandardItem
from powerdb.models.test_run import TestRecord, TestRun
from powerdb.repositories.base import Repository


class MeasurementRepository(Repository[Measurement]):
    model = Measurement

    def query_for_comparison(
        self,
        *,
        metric: str,
        sample_id: Optional[int] = None,
        standard_item_id: Optional[int] = None,
    ) -> list[dict]:
        """按指标拉取历史测量值（跨样品 / 跨批次），用于横向对比。

        返回字典列表，Service 层可转 DataFrame 或直接给看板 / AI 用。
        稳定字段：sample_code / run_no / item_name / value / unit / started_at。
        """
        stmt = (
            select(
                Measurement.id,
                Measurement.metric,
                Measurement.value,
                Measurement.unit,
                Measurement.created_at,
                TestRun.run_no,
                TestRun.started_at,
                Sample.code.label("sample_code"),
                StandardItem.name.label("item_name"),
            )
            .join(TestRecord, Measurement.test_record_id == TestRecord.id)
            .join(TestRun, TestRecord.test_run_id == TestRun.id)
            .join(Sample, TestRun.sample_id == Sample.id)
            .join(StandardItem, TestRecord.standard_item_id == StandardItem.id)
            .where(Measurement.metric == metric)
        )
        if sample_id is not None:
            stmt = stmt.where(Sample.id == sample_id)
        if standard_item_id is not None:
            stmt = stmt.where(StandardItem.id == standard_item_id)

        stmt = stmt.order_by(TestRun.started_at, Measurement.id)
        return [dict(m) for m in self.session.execute(stmt).mappings()]