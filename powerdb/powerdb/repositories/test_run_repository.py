"""测试运行仓储：按样品 / 批次检索试验。"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from powerdb.models.test_run import TestRecord, TestRun
from powerdb.repositories.base import Repository


class TestRunRepository(Repository[TestRun]):
    model = TestRun

    def list_by_sample(self, sample_id: int, limit: Optional[int] = None) -> list[TestRun]:
        stmt = select(TestRun).where(TestRun.sample_id == sample_id).order_by(TestRun.started_at)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def get_with_records(self, run_id: int) -> Optional[TestRun]:
        """一次取回试验及其所有测试记录（避免 N+1 查询）。"""
        return self.session.scalar(
            select(TestRun)
            .options(selectinload(TestRun.records).selectinload(TestRecord.standard_item))
            .where(TestRun.id == run_id)
        )