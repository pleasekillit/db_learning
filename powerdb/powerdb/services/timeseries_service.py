"""时序数据服务：通道创建、批量写入、读取与降采样。

高频原始波形仍建议落文件（raw_path 指向 Parquet/NPY），
本服务负责元数据入库 + 中低频 / 降采样点的库内读写。
"""
from __future__ import annotations

from typing import Iterable, Optional

from powerdb.core.engine import session_scope
from powerdb.models.timeseries import TimeSeriesChannel
from powerdb.repositories.timeseries_repository import TimeSeriesRepository


def create_channel(
    test_record_id: int,
    name: str,
    *,
    unit: Optional[str] = None,
    sample_rate: Optional[float] = None,
    start_time: Optional[float] = None,
    raw_path: Optional[str] = None,
    data: Optional[Iterable[tuple[float, float]]] = None,
) -> int:
    """创建时序通道，可一次性批量写入采样点。返回通道 id。"""
    with session_scope() as session:
        repo = TimeSeriesRepository(session)
        channel = TimeSeriesChannel(
            test_record_id=test_record_id,
            name=name,
            unit=unit,
            sample_rate=sample_rate,
            start_time=start_time,
            raw_path=raw_path,
        )
        repo.add(channel)
        session.flush()  # 立即拿到 channel.id
        if data is not None:
            points = list(data)
            repo.bulk_insert_points(channel.id, points)
            channel.point_count = len(points)
        return channel.id


def read_channel(
    channel_id: int,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> list[tuple[float, float]]:
    """读取通道采样点，返回 [(t, value), ...]。"""
    with session_scope() as session:
        points = TimeSeriesRepository(session).get_channel_points(channel_id, start, end)
        return [(p.t, p.value) for p in points]


def to_dataframe(channel_id: int):
    """把通道采样点读成 DataFrame（需 pandas），便于画图与进一步分析。"""
    import pandas as pd

    return pd.DataFrame(read_channel(channel_id), columns=["t", "value"])


def resample(channel_id: int, window: int) -> list[tuple[float, float]]:
    """按窗口均值降采样，返回 [(t_mean, value_mean), ...]。

    window = 每窗口包含的原始点数。用于把高频库内点降到看板可绘的尺度。
    """
    import pandas as pd

    df = to_dataframe(channel_id)
    if df.empty:
        return []
    grouped = df.groupby(df.index // window).agg(t=("t", "mean"), value=("value", "mean"))
    return list(grouped[["t", "value"]].itertuples(index=False, name=None))