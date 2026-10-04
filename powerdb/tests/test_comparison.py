"""历史横向对比 + 时序读写测试。"""
import pytest

from powerdb.config import DatabaseConfig
from powerdb.core.engine import create_schema, init_engine, session_scope
from powerdb.models import (
    Measurement,
    Project,
    Sample,
    Standard,
    StandardItem,
    TestRecord,
    TestRun,
)
from powerdb.services.comparison_service import compare_metric
from powerdb.services.timeseries_service import create_channel, read_channel


@pytest.fixture()
def seeded(tmp_path):
    init_engine(DatabaseConfig(url=f"sqlite:///{tmp_path / 'test.db'}"))
    create_schema(drop=True)

    with session_scope() as session:
        project = Project(name="P")
        sa = Sample(code="A", name="样品A", project=project)
        sb = Sample(code="B", name="样品B", project=project)
        std = Standard(code="GB", name="标准")
        item = StandardItem(code="EFF", name="效率", unit="%", standard=std)
        session.add_all([project, sa, sb, std, item])
        session.flush()

        r1 = TestRun(sample_id=sa.id, run_no="R1")
        r2 = TestRun(sample_id=sb.id, run_no="R2")
        session.add_all([r1, r2])
        session.flush()

        c1 = TestRecord(test_run_id=r1.id, standard_item_id=item.id)
        c2 = TestRecord(test_run_id=r2.id, standard_item_id=item.id)
        session.add_all([c1, c2])
        session.flush()

        session.add(Measurement(test_record_id=c1.id, metric="efficiency", value=97.0, unit="%"))
        session.add(Measurement(test_record_id=c2.id, metric="efficiency", value=95.0, unit="%"))
        session.flush()
        return c1.id, c2.id


def test_comparison(seeded):
    rows = compare_metric("efficiency")
    assert len(rows) == 2
    assert {r["sample_code"] for r in rows} == {"A", "B"}


def test_timeseries_roundtrip(seeded):
    cid, _ = seeded
    n = 500
    channel_id = create_channel(
        cid, "Ia", unit="A", sample_rate=1000.0,
        data=[(i / 1000, float(i)) for i in range(n)],
    )
    points = read_channel(channel_id)
    assert len(points) == n
    assert points[0] == (0.0, 0.0)
    assert points[-1][0] == pytest.approx((n - 1) / 1000)