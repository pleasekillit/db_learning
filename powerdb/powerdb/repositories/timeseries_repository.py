"""时序数据仓储：通道检索与采样点读写。"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import insert, select

from powerdb.models.timeseries import TimeSeriesChannel, TimeSeriesPoint
from powerdb.repositories.base import Repository


class TimeSeriesRepository(Repository[TimeSeriesChannel]):
    model = TimeSeriesChannel

    def get_channel_points(
        self,
        channel_id: int,
        start: Optional[float] = None,
        end: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[TimeSeriesPoint]:
        """按通道（可加时间范围）读取采样点，按时间升序。"""
        stmt = select(TimeSeriesPoint).where(TimeSeriesPoint.channel_id == channel_id)
        if start is not None:
            stmt = stmt.where(TimeSeriesPoint.t >= start)
        if end is not None:
            stmt = stmt.where(TimeSeriesPoint.t <= end)
        stmt = stmt.order_by(TimeSeriesPoint.t)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def bulk_insert_points(self, channel_id: int, data: Iterable[tuple[float, float]]) -> None:
        """批量写入采样点。

        与逐条 `session.add` 相比，bulk insert 一次往返写入上千点，
        是时序写入性能的关键（阶段4会对此做对比验证）。
        """
        rows = [{"channel_id": channel_id, "t": t, "value": value} for t, value in data]
        if rows:
            self.session.execute(insert(TimeSeriesPoint), rows)