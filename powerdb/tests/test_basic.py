"""基础读写测试：证明骨架端到端可跑。"""
import pytest
from sqlalchemy import func, select

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


@pytest.fixture()
def db(tmp_path):
    init_engine(DatabaseConfig(url=f"sqlite:///{tmp_path / 'test.db'}"))
    create_schema(drop=True)
    yield
    create_schema(drop=True)


def test_write_and_read(db):
    with session_scope() as session:
        project = Project(name="P1")
        sample = Sample(code="S1", name="样品1", project=project)
        std = Standard(code="GB1", name="标准1")
        item = StandardItem(code="I1", name="测试项1", unit="%", standard=std)
        session.add_all([project, sample, std, item])
        session.flush()

        run = TestRun(sample_id=sample.id, run_no="R1")
        session.add(run)
        session.flush()
        rec = TestRecord(test_run_id=run.id, standard_item_id=item.id, status="pass")
        session.add(rec)
        session.flush()
        session.add(Measurement(test_record_id=rec.id, metric="efficiency", value=97.0, unit="%"))

    with session_scope() as session:
        run_count = session.scalar(select(func.count()).select_from(TestRun))
        assert run_count == 1

        m = session.scalar(select(Measurement).where(Measurement.metric == "efficiency"))
        assert m is not None
        assert m.value == 97.0