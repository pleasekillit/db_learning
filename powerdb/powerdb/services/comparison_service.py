"""历史横向对比服务。

把「同一指标在不同样品 / 不同批次 / 不同时间」的测量结果汇总，
供前端看板、历史对比、AI 分析共用同一处业务逻辑。
"""
from __future__ import annotations

from typing import Optional

from powerdb.core.engine import session_scope
from powerdb.models.standard import StandardItem
from powerdb.repositories.result_repository import MeasurementRepository


def compare_metric(
    metric: str,
    *,
    sample_id: Optional[int] = None,
    standard_item_id: Optional[int] = None,
    as_dataframe: bool = False,
):
    """横向对比某个指标的历史测量结果。

    返回字典列表；as_dataframe=True 时返回 pandas.DataFrame（需安装 pandas）。
    """
    with session_scope() as session:
        rows = MeasurementRepository(session).query_for_comparison(
            metric=metric,
            sample_id=sample_id,
            standard_item_id=standard_item_id,
        )
    if as_dataframe:
        import pandas as pd  # noqa: F401  延迟导入，pandas 可选

        return pd.DataFrame(rows)
    return rows


def summarize_metric(metric: str, *, sample_id: Optional[int] = None) -> dict:
    """返回某指标跨批次的概要统计：count / min / max / mean / std。"""
    import pandas as pd

    df = compare_metric(metric, sample_id=sample_id, as_dataframe=True)
    if df.empty:
        return {}
    values = df["value"].dropna()
    return {
        "metric": metric,
        "count": int(values.size),
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "std": float(values.std(ddof=0)),
    }


def judge_metric(
    metric: str,
    *,
    sample_id: Optional[int] = None,
    standard_item_id: Optional[int] = None,
) -> list[dict]:
    """按标准限值判定某指标各批次是否合格（业务判定规则）。

    判定逻辑：先查出该测试项的 limit_min / limit_max，再逐行对比：
        - 没有限值或没有测量值 -> "未判"
        - 低于下限 或 高于上限 -> "不合格"
        - 其余                 -> "合格"

    返回每行：run_no / sample_code / item_name / value / unit /
              limit_min / limit_max / verdict（合格/不合格/未判）。
    """
    rows = compare_metric(metric, sample_id=sample_id, standard_item_id=standard_item_id)

    limit_min = limit_max = None
    if standard_item_id is not None:
        with session_scope() as session:
            item = session.get(StandardItem, standard_item_id)
            if item is not None:
                limit_min, limit_max = item.limit_min, item.limit_max

    result: list[dict] = []
    for r in rows:
        value = r["value"]
        if value is None or (limit_min is None and limit_max is None):
            verdict = "未判"
        elif limit_min is not None and value < limit_min:
            verdict = "不合格"
        elif limit_max is not None and value > limit_max:
            verdict = "不合格"
        else:
            verdict = "合格"
        result.append({
            "run_no": r["run_no"],
            "sample_code": r["sample_code"],
            "item_name": r["item_name"],
            "value": value,
            "unit": r["unit"],
            "limit_min": limit_min,
            "limit_max": limit_max,
            "verdict": verdict,
        })
    return result