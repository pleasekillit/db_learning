"""Python <-> SQL 类型映射测试：用断言钉死「写入 = 读回」。"""
from datetime import datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

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
from powerdb.schemas.result_schema import MeasurementCreate
from powerdb.services.timeseries_service import create_channel, read_channel


@pytest.fixture()
def db(tmp_path):
    init_engine(DatabaseConfig(url=f"sqlite:///{tmp_path / 'test.db'}"))
    create_schema(drop=True)
    yield


def _seed() -> tuple[int, int]:
    """写入一组跨类型数据，返回 (run_id, record_id)。"""
    with session_scope() as s:
        project = Project(name="P")
        sample = Sample(code="S1", name="样品1", project=project)
        std = Standard(code="GB", name="标准")
        item = StandardItem(code="EFF", name="效率", unit="%", standard=std)
        s.add_all([project, sample, std, item])
        s.flush()

        run = TestRun(
            sample_id=sample.id,
            run_no="R1",
            environment={"temp_c": 25.0, "rh": 45, "passed": True, "seq": [1, 2, 3]},
        )
        s.add(run)
        s.flush()

        rec = TestRecord(
            test_run_id=run.id,
            standard_item_id=item.id,
            status="pass",
            started_at=datetime(2026, 9, 26, 10, 0, 0),
        )
        s.add(rec)
        s.flush()
        s.add(Measurement(test_record_id=rec.id, metric="efficiency", value=97.2, unit="%"))
        return run.id, rec.id


def test_scalar_and_dict_roundtrip(db):
    run_id, _ = _seed()
    with session_scope() as s:
        run = s.get(TestRun, run_id)
        # dict -> JSON 列往返
        assert isinstance(run.environment, dict)
        assert run.environment["passed"] is True          # bool 保真
        assert run.environment["seq"] == [1, 2, 3]        # list 保真
        assert run.environment["temp_c"] == 25.0          # float 保真

        # 标量往返
        m = s.scalar(select(Measurement).where(Measurement.metric == "efficiency"))
        assert isinstance(m.value, float)                 # Float 读回 float
        assert m.value == pytest.approx(97.2)


def test_datetime_roundtrip(db):
    _, rec_id = _seed()
    with session_scope() as s:
        rec = s.get(TestRecord, rec_id)
        assert isinstance(rec.started_at, datetime)       # DateTime 读回 datetime
        assert rec.started_at == datetime(2026, 9, 26, 10, 0, 0)


def test_list_tuple_long_table(db):
    _, rec_id = _seed()
    data = [(0.0, 10.0), (0.001, 10.1), (0.002, 10.2)]
    channel_id = create_channel(rec_id, "Ia", unit="A", data=data)
    points = read_channel(channel_id)
    assert len(points) == 3
    assert isinstance(points[0], tuple)                   # 行读回 tuple
    assert isinstance(points[0][0], float)                # 每列是标量 float
    assert points[0] == (0.0, 10.0)


def test_pydantic_coercion_and_reject(db):
    # str -> float 强转成功
    ok = MeasurementCreate(test_record_id=1, metric="efficiency", value="97.2")
    assert isinstance(ok.value, float)
    assert ok.value == 97.2

    # 无法转 float 的入参被拒绝
    with pytest.raises(ValidationError):
        MeasurementCreate(test_record_id=1, metric="efficiency", value="abc")