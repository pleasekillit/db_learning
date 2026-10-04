"""导出（业务视图）仓储：为 Excel 导出提供「业务看得懂」的扁平行。

和 result_repository 一样，复杂 JOIN 集中在仓储层；这里把「用例执行记录」
拼成一张业务视图，字段键与 exporters/field_map.py 的 CASE_RECORD_FIELDS 对齐，
供导出层直接写到 Excel。数据键一旦约定好，「表格设计」与「数据库设计」就不再割裂。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from powerdb.models.data_file import DataFile
from powerdb.models.project import Sample
from powerdb.models.standard import StandardItem
from powerdb.models.test_run import TestRecord, TestRun
from powerdb.repositories.base import Repository


class ExportRepository(Repository[TestRecord]):
    model = TestRecord

    def query_case_records(
        self,
        *,
        run_no: Optional[str] = None,
        sample_code: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """把「用例执行记录」拼成业务视图行。

        返回稳定键（与 field_map.py 对齐）：
            case_code / case_name / sample_code / run_no /
            started_at / status / files
        """
        stmt = (
            select(TestRecord, TestRun, Sample, StandardItem)
            .join(TestRun, TestRecord.test_run_id == TestRun.id)
            .join(Sample, TestRun.sample_id == Sample.id)
            .join(StandardItem, TestRecord.standard_item_id == StandardItem.id)
            .options(selectinload(TestRecord.files))  # 一次取回文件，避免 N+1
        )
        if run_no is not None:
            stmt = stmt.where(TestRun.run_no == run_no)
        if sample_code is not None:
            stmt = stmt.where(Sample.code == sample_code)
        if status is not None:
            stmt = stmt.where(TestRecord.status == status)

        stmt = stmt.order_by(TestRun.started_at, TestRecord.started_at, TestRecord.id)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = self.session.execute(stmt).all()
        return [self._to_row(rec, run, sample, item) for rec, run, sample, item in result]

    @staticmethod
    def _to_row(
        rec: TestRecord, run: TestRun, sample: Sample, item: StandardItem
    ) -> dict:
        files = "; ".join(f.name for f in rec.files) if rec.files else ""
        return {
            "case_code": item.code,
            "case_name": item.name,
            "sample_code": sample.code,
            "run_no": run.run_no,
            "started_at": rec.started_at,
            "status": rec.status,
            "files": files,
        }